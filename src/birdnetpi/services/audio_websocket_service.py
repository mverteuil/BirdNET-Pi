from __future__ import annotations

import asyncio
import atexit
import logging
import os
import signal
from types import FrameType
from typing import Any

import websockets
from websockets.asyncio.server import serve

from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

logger = logging.getLogger(__name__)


class AudioWebSocketService:
    """Service that reads audio from FIFO and streams to WebSocket clients."""

    def __init__(self, config_path: str | None = None, fifo_base_path: str | None = None) -> None:
        self._shutdown_flag = False
        self._fifo_livestream_path = None
        self._fifo_livestream_fd = None
        self._websocket_server = None
        self._audio_clients = set()
        self._processing_active = False

        # Initialize paths
        file_resolver = FilePathResolver()
        self._config_path = config_path or file_resolver.get_birdnetpi_config_path()
        fifo_base = fifo_base_path or file_resolver.get_fifo_base_path()
        self._fifo_livestream_path = os.path.join(fifo_base, "birdnet_audio_livestream.fifo")

        logger.info("AudioWebSocketService initialized.")

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals."""
        logger.info("Signal %s received, initiating graceful shutdown...", signum)
        self._shutdown_flag = True

    def _cleanup_fifo_and_service(self) -> None:
        """Clean up FIFO and WebSocket server resources."""
        if self._fifo_livestream_fd:
            os.close(self._fifo_livestream_fd)
            logger.info("Closed FIFO: %s", self._fifo_livestream_path)
            self._fifo_livestream_fd = None
        if self._websocket_server:
            self._websocket_server.close()
            logger.info("WebSocket server closed")

    async def _extract_websocket_path(self, websocket: Any) -> str:
        """Extract the path from a WebSocket connection."""
        path = None
        try:
            if hasattr(websocket, "path"):
                path = websocket.path
            elif hasattr(websocket, "request") and hasattr(websocket.request, "path"):
                path = websocket.request.path
            elif hasattr(websocket, "request_headers"):
                for name, value in websocket.request_headers.raw_items():
                    if name.lower() == b":path":
                        path = value.decode("utf-8")
                        break

            if path is None:
                logger.warning("Could not extract path from websocket, defaulting to /")
                path = "/"

            logger.info("WebSocket connection attempt with path: '%s'", path)
        except Exception as e:
            logger.error("Error extracting path from websocket: %s", e, exc_info=True)
            path = "/"

        return path

    async def _handle_audio_websocket(self, websocket: Any) -> None:
        """Handle a WebSocket connection for audio streaming."""
        self._audio_clients.add(websocket)
        logger.info("Audio WebSocket client connected. Total: %d", len(self._audio_clients))
        try:
            async for _message in websocket:
                # Keep connection alive
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._audio_clients.discard(websocket)
            logger.info(
                "Audio WebSocket client disconnected. Remaining: %d", len(self._audio_clients)
            )

    async def _websocket_handler(self, websocket: Any) -> None:
        """Route WebSocket connections based on path."""
        path = await self._extract_websocket_path(websocket)

        if path == "/ws/audio":
            await self._handle_audio_websocket(websocket)
        elif path == "/ws/spectrogram":
            logger.info("Spectrogram request redirected - handled by separate service on port 9002")
            await websocket.close(code=4003, reason="Spectrogram moved to dedicated service")
        else:
            logger.warning("Unknown WebSocket endpoint: %s", path)
            await websocket.close(code=4004, reason="Unknown endpoint")

    async def _broadcast_audio_data(self, audio_data_bytes: bytes) -> None:
        """Broadcast raw PCM audio data to all connected audio clients."""
        if self._audio_clients:
            try:
                # Create header for client to understand PCM format
                data_length = len(audio_data_bytes)
                header = data_length.to_bytes(4, byteorder="little")
                pcm_packet = header + audio_data_bytes

                # Broadcast to all connected clients
                disconnected = set()
                for client in self._audio_clients:
                    try:
                        await client.send(pcm_packet)
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)

                # Remove disconnected clients
                self._audio_clients -= disconnected

            except Exception as e:
                logger.error("Error broadcasting audio data: %s", e, exc_info=True)

    async def _fifo_reading_loop(self) -> None:
        """Read from FIFO and process audio data."""
        while not self._shutdown_flag:
            try:
                buffer_size = 4096
                if self._fifo_livestream_fd is not None:
                    audio_data_bytes = os.read(self._fifo_livestream_fd, buffer_size)
                else:
                    # Skip if FIFO not open
                    await asyncio.sleep(0.01)
                    continue

                if audio_data_bytes:
                    if self._audio_clients:
                        if not self._processing_active:
                            self._processing_active = True
                            try:
                                await self._broadcast_audio_data(audio_data_bytes)
                            finally:
                                self._processing_active = False
                else:
                    await asyncio.sleep(0.01)

            except BlockingIOError:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error("Error reading from FIFO or broadcasting data: %s", e, exc_info=True)
                await asyncio.sleep(0.1)

    async def start(self) -> None:
        """Start the audio WebSocket service."""
        logger.info("Starting AudioWebSocketService.")

        # Register signal handlers and cleanup
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup_fifo_and_service)

        try:
            # Load configuration
            config_parser = ConfigFileParser(self._config_path)
            _ = config_parser.load_config()
            logger.info("Configuration loaded successfully.")

            # Open FIFO for reading
            if self._fifo_livestream_path is not None:
                self._fifo_livestream_fd = os.open(
                    self._fifo_livestream_path, os.O_RDONLY | os.O_NONBLOCK
                )
            logger.info("Opened FIFO for reading: %s", self._fifo_livestream_path)

            # Start WebSocket server
            self._websocket_server = await serve(
                self._websocket_handler, "0.0.0.0", 9001, logger=logger
            )
            logger.info("WebSocket server started on 0.0.0.0:9001")

            # Create FIFO reading task
            self._fifo_task = asyncio.create_task(self._fifo_reading_loop())

        except FileNotFoundError:
            logger.error(
                "FIFO not found at %s. Ensure audio_capture is running and creating it.",
                self._fifo_livestream_path,
            )
            raise
        except Exception as e:
            logger.error("An error occurred starting AudioWebSocketService: %s", e, exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop the audio WebSocket service."""
        logger.info("Stopping AudioWebSocketService.")
        self._shutdown_flag = True

        # Cancel FIFO task
        if hasattr(self, "_fifo_task"):
            self._fifo_task.cancel()
            try:
                await self._fifo_task
            except asyncio.CancelledError:
                pass

        self._cleanup_fifo_and_service()

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        while not self._shutdown_flag:
            await asyncio.sleep(0.1)
