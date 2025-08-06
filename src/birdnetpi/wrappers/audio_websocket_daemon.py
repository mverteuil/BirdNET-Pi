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

from birdnetpi.services.audio_websocket_service import AudioWebSocketService
from birdnetpi.services.spectrogram_service import SpectrogramService
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
_audio_websocket_service = None
_spectrogram_service = None
_websocket_server = None
_audio_clients = set()
_spectrogram_clients = set()


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo_and_service() -> None:
    global _fifo_livestream_fd, _fifo_livestream_path, _audio_websocket_service, _spectrogram_service, _websocket_server
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
        _spectrogram_clients.add(websocket)
        logger.info("Spectrogram WebSocket client connected. Total: %d", len(_spectrogram_clients))
        
        # Create a mock WebSocket object that matches FastAPI WebSocket interface
        class MockWebSocket:
            def __init__(self, websocket):
                self.websocket = websocket
            
            async def send_json(self, data):
                json_str = json.dumps(data)
                await self.websocket.send(json_str)
        
        mock_ws = MockWebSocket(websocket)
        
        # Register client with the SpectrogramService
        if _spectrogram_service:
            await _spectrogram_service.connect_websocket(mock_ws)
        
        try:
            async for message in websocket:
                # Keep connection alive
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            _spectrogram_clients.discard(websocket)
            # Unregister from SpectrogramService
            if _spectrogram_service:
                await _spectrogram_service.disconnect_websocket(mock_ws)
            logger.info("Spectrogram WebSocket client disconnected. Remaining: %d", len(_spectrogram_clients))
    
    else:
        logger.warning("Unknown WebSocket endpoint: %s", path)
        await websocket.close(code=4004, reason="Unknown endpoint")


async def _broadcast_audio_data(audio_data_bytes: bytes):
    """Broadcast MP3 audio data to all connected audio clients."""
    global _audio_clients
    if _audio_clients:
        # Encode to MP3 for broadcasting - use thread pool to avoid blocking
        try:
            def encode_mp3(audio_bytes):
                from pydub import AudioSegment
                from io import BytesIO
                
                # Create AudioSegment from raw bytes
                audio_segment = AudioSegment(
                    audio_bytes,
                    sample_width=2,  # 2 bytes for int16
                    frame_rate=48000,  # Using config sample rate
                    channels=1,
                )
                
                # Export to MP3
                buffer = BytesIO()
                audio_segment.export(buffer, format="mp3")
                return buffer.getvalue()
            
            # Run MP3 encoding in thread pool to avoid blocking the async loop
            loop = asyncio.get_event_loop()
            mp3_data = await loop.run_in_executor(None, encode_mp3, audio_data_bytes)
            
            # Broadcast to all connected clients
            disconnected = set()
            for client in _audio_clients:
                try:
                    await client.send(mp3_data)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
            
            # Remove disconnected clients
            _audio_clients -= disconnected
            
        except Exception as e:
            logger.error("Error broadcasting audio data: %s", e, exc_info=True)


async def _broadcast_spectrogram_data(spectrogram_data: dict):
    """Broadcast spectrogram data to all connected spectrogram clients."""
    global _spectrogram_clients
    if _spectrogram_clients:
        try:
            json_data = json.dumps(spectrogram_data)
            
            # Broadcast to all connected clients
            disconnected = set()
            for client in _spectrogram_clients:
                try:
                    await client.send(json_data)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
            
            # Remove disconnected clients
            _spectrogram_clients -= disconnected
            
        except Exception as e:
            logger.error("Error broadcasting spectrogram data: %s", e, exc_info=True)


async def _fifo_reading_loop():
    """Read from FIFO and process audio data."""
    global _fifo_livestream_fd, _spectrogram_service
    
    while not _shutdown_flag:
        try:
            buffer_size = 4096  # Must match producer's write size
            audio_data_bytes = os.read(_fifo_livestream_fd, buffer_size)

            if audio_data_bytes:
                # Broadcast raw audio data to audio clients
                await _broadcast_audio_data(audio_data_bytes)
                
                # Process spectrogram data
                spectrogram_data = await _spectrogram_service.process_audio_chunk(audio_data_bytes)
                if spectrogram_data:
                    await _broadcast_spectrogram_data(spectrogram_data)
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
    global _fifo_livestream_path, _fifo_livestream_fd, _audio_websocket_service, _spectrogram_service, _websocket_server
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

        # Get configuration
        samplerate = config.sample_rate
        channels = config.audio_channels

        # Create spectrogram service for processing
        _spectrogram_service = SpectrogramService(
            sample_rate=samplerate,
            channels=channels,
            window_size=1024,
            overlap=0.75,
            update_rate=15.0,
        )
        logger.info("SpectrogramService instantiated and ready for connections.")

        # Start WebSocket server on port 9001 (bind to all interfaces for Docker/Caddy)
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
