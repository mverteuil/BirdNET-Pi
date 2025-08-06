import asyncio
import atexit
import json
import logging
import os
import signal
import time
from types import FrameType

import websockets
from websockets.asyncio.server import serve

from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_livestream_path = None
_fifo_livestream_fd = None
_websocket_server = None
_audio_clients = set()
_processing_active = False  # Track if we're currently processing to avoid buildup


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo_and_service() -> None:
    global _fifo_livestream_fd, _fifo_livestream_path, _websocket_server
    if _fifo_livestream_fd:
        os.close(_fifo_livestream_fd)
        logger.info("Closed FIFO: %s", _fifo_livestream_path)
        _fifo_livestream_fd = None
    if _websocket_server:
        _websocket_server.close()
        logger.info("WebSocket server closed")


async def _websocket_handler(websocket):
    """Route WebSocket connections based on path."""
    global _audio_clients, _spectrogram_clients
    
    # Debug: Log what attributes are available
    logger.debug("WebSocket attributes: %s", [attr for attr in dir(websocket) if not attr.startswith('_')][:10])
    
    # The new websockets library passes the path differently
    # We need to check multiple possible locations
    path = None
    
    try:
        # Method 1: Direct path attribute (some versions)
        if hasattr(websocket, 'path'):
            path = websocket.path
            logger.info("Got path from websocket.path: %s", path)
        # Method 2: From request object
        elif hasattr(websocket, 'request'):
            if hasattr(websocket.request, 'path'):
                path = websocket.request.path
                logger.info("Got path from websocket.request.path: %s", path)
        # Method 3: From request_headers (HTTP/2 style)
        elif hasattr(websocket, 'request_headers'):
            for name, value in websocket.request_headers.raw_items():
                logger.debug("Header: %s = %s", name, value)
                if name.lower() == b':path':
                    path = value.decode('utf-8')
                    logger.info("Got path from request_headers: %s", path)
                    break
        
        # If we still don't have a path, log all attributes for debugging
        if path is None:
            logger.warning("Could not find path in websocket object. Available attributes: %s", 
                         [attr for attr in dir(websocket) if not attr.startswith('_')])
            # Default to root which will trigger the unknown endpoint handler
            path = "/"
            
        logger.info("WebSocket connection attempt with final path: '%s'", path)
        
    except Exception as e:
        logger.error("Error extracting path from websocket: %s", e, exc_info=True)
        path = "/"
    
    if path == "/ws/audio":
        _audio_clients.add(websocket)
        logger.info("Audio WebSocket client connected. Total: %d", len(_audio_clients))
        try:
            async for message in websocket:
                # Keep connection alive
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            _audio_clients.discard(websocket)
            logger.info("Audio WebSocket client disconnected. Remaining: %d", len(_audio_clients))
    
    elif path == "/ws/spectrogram":
        # Spectrogram now handled by separate service on port 9002
        logger.info("Spectrogram request redirected - should be handled by separate service on port 9002")
        await websocket.close(code=4003, reason="Spectrogram moved to dedicated service")
    
    else:
        logger.warning("Unknown WebSocket endpoint: %s", path)
        await websocket.close(code=4004, reason="Unknown endpoint")


async def _broadcast_audio_data(audio_data_bytes: bytes):
    """Broadcast raw PCM audio data to all connected audio clients - no encoding needed!"""
    global _audio_clients
    if _audio_clients:
        try:
            # Send raw PCM data directly - no CPU-intensive encoding!
            # The browser can decode PCM directly using Web Audio API
            
            # Create a simple header for the client to understand the format
            # Format: 4 bytes length + PCM data
            data_length = len(audio_data_bytes)
            header = data_length.to_bytes(4, byteorder='little')
            pcm_packet = header + audio_data_bytes
            
            # Broadcast to all connected clients (much faster than MP3 encoding)
            disconnected = set()
            for client in _audio_clients:
                try:
                    await client.send(pcm_packet)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
            
            # Remove disconnected clients
            _audio_clients -= disconnected
            
        except Exception as e:
            logger.error("Error broadcasting audio data: %s", e, exc_info=True)


# Spectrogram broadcasting now handled by separate dedicated service


async def _fifo_reading_loop():
    """Read from FIFO and process audio data only. Spectrogram handled by separate service."""
    global _fifo_livestream_fd, _processing_active
    
    while not _shutdown_flag:
        try:
            buffer_size = 4096  # Must match producer's write size
            audio_data_bytes = os.read(_fifo_livestream_fd, buffer_size)

            if audio_data_bytes:
                # Only process audio if we have audio clients (spectrogram handled separately)
                if _audio_clients:
                    # Skip processing if we're already busy to prevent latency buildup
                    if not _processing_active:
                        _processing_active = True
                        try:
                            # Only handle audio broadcasting - much faster than before
                            await _broadcast_audio_data(audio_data_bytes)
                        finally:
                            _processing_active = False
                # If no clients, just drain the FIFO to prevent buildup
            else:
                await asyncio.sleep(0.01)

        except BlockingIOError:
            await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(
                "Error reading from FIFO or broadcasting data: %s", e, exc_info=True
            )
            await asyncio.sleep(0.1)


async def _main_async() -> None:
    """Async main function to handle FIFO reading and WebSocket server."""
    global _fifo_livestream_path, _fifo_livestream_fd, _websocket_server
    logger.info("Starting audio websocket wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifo_and_service)

    file_resolver = FilePathResolver()
    fifo_base_path = file_resolver.get_fifo_base_path()
    _fifo_livestream_path = os.path.join(fifo_base_path, "birdnet_audio_livestream.fifo")

    try:
        # Load configuration
        config_path = file_resolver.get_birdnetpi_config_path()
        config_parser = ConfigFileParser(config_path)
        config = config_parser.load_config()
        logger.info("Configuration loaded successfully.")

        # Open FIFO for reading
        _fifo_livestream_fd = os.open(_fifo_livestream_path, os.O_RDONLY | os.O_NONBLOCK)
        logger.info("Opened FIFO for reading: %s", _fifo_livestream_path)

        # Start WebSocket server on port 9001 for audio only (bind to all interfaces for Docker/Caddy)
        _websocket_server = await serve(
            _websocket_handler,
            "0.0.0.0",
            9001,
            logger=logger
        )
        logger.info("WebSocket server started on 0.0.0.0:9001")

        # Create a task for the FIFO reading loop
        fifo_task = asyncio.create_task(_fifo_reading_loop())
        
        # Wait for shutdown signal
        while not _shutdown_flag:
            await asyncio.sleep(0.1)
        
        # Cancel FIFO task
        fifo_task.cancel()
        try:
            await fifo_task
        except asyncio.CancelledError:
            pass

    except FileNotFoundError:
        logger.error(
            "FIFO not found at %s. Ensure audio_capture is running and creating it.",
            _fifo_livestream_path,
        )
    except Exception as e:
        logger.error("An error occurred in the audio websocket wrapper: %s", e, exc_info=True)
    finally:
        _cleanup_fifo_and_service()


def main() -> None:
    """Run the audio websocket wrapper."""
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error("Error in main: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
