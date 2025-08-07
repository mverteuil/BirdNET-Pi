#!/usr/bin/env python3
"""Dedicated WebSocket daemon for spectrogram processing.

This service runs in a separate process to handle CPU-intensive spectrogram
generation without blocking the main audio pipeline. It connects to the same
FIFO and serves spectrogram data via WebSocket on a dedicated port.
"""

import asyncio
import atexit
import json
import logging
import os
import signal
from types import FrameType

import websockets
from websockets.asyncio.server import serve

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
_spectrogram_service = None
_websocket_server = None
_spectrogram_clients = set()


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo_and_service() -> None:
    global _fifo_livestream_fd, _fifo_livestream_path, _spectrogram_service, _websocket_server
    if _fifo_livestream_fd:
        os.close(_fifo_livestream_fd)
        logger.info("Closed FIFO: %s", _fifo_livestream_path)
        _fifo_livestream_fd = None
    if _websocket_server:
        _websocket_server.close()
        logger.info("Spectrogram WebSocket server closed")


async def _websocket_handler(websocket):
    """Handle WebSocket connections for spectrogram data."""
    global _spectrogram_clients, _spectrogram_service

    logger.info("Spectrogram WebSocket client connected from %s", websocket.remote_address)
    _spectrogram_clients.add(websocket)

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
        logger.info(
            "Spectrogram WebSocket client disconnected. Remaining: %d", len(_spectrogram_clients)
        )


async def _fifo_reading_loop():
    """Read from FIFO and process spectrogram data only."""
    global _fifo_livestream_fd, _spectrogram_service

    logger.info("Starting FIFO reading loop for spectrogram processing")

    while not _shutdown_flag:
        try:
            buffer_size = 4096  # Must match producer's write size
            audio_data_bytes = os.read(_fifo_livestream_fd, buffer_size)

            if audio_data_bytes:
                # Only process if we have spectrogram clients
                if _spectrogram_clients and _spectrogram_service:
                    # Process spectrogram in this dedicated service
                    spectrogram_data = await _spectrogram_service.process_audio_chunk(
                        audio_data_bytes
                    )
                    # Note: spectrogram_service.process_audio_chunk already sends to clients
            else:
                await asyncio.sleep(0.01)

        except BlockingIOError:
            await asyncio.sleep(0.01)
        except Exception as e:
            logger.error("Error in spectrogram FIFO reading: %s", e, exc_info=True)
            await asyncio.sleep(0.1)


async def _main_async() -> None:
    """Async main function for dedicated spectrogram service."""
    global _fifo_livestream_path, _fifo_livestream_fd, _spectrogram_service, _websocket_server
    logger.info("Starting dedicated spectrogram WebSocket service.")

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

        # Start WebSocket server on port 9002 for spectrogram only
        _websocket_server = await serve(_websocket_handler, "0.0.0.0", 9002, logger=logger)
        logger.info("Spectrogram WebSocket server started on 0.0.0.0:9002")

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
        logger.error("An error occurred in the spectrogram websocket service: %s", e, exc_info=True)
    finally:
        _cleanup_fifo_and_service()


def main() -> None:
    """Run the spectrogram websocket service."""
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error("Error in main: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
