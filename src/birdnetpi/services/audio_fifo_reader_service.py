import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from birdnetpi.services.audio_websocket_service import AudioWebSocketService
    from birdnetpi.services.spectrogram_service import SpectrogramService

logger = logging.getLogger(__name__)


class AudioFifoReaderService:
    """Service for reading audio data from livestream FIFO and feeding it to WebSocket service."""

    def __init__(
        self,
        fifo_path: str,
        audio_websocket_service: "AudioWebSocketService",
        spectrogram_service: "SpectrogramService | None" = None,
    ) -> None:
        self.fifo_path = fifo_path
        self.audio_websocket_service = audio_websocket_service
        self.spectrogram_service = spectrogram_service
        self.running = False
        self.task = None
        logger.info("AudioFifoReaderService initialized for FIFO: %s", fifo_path)

    async def start(self) -> None:
        """Start the FIFO reader task."""
        if self.running:
            logger.warning("AudioFifoReaderService is already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._read_fifo_loop())
        logger.info("AudioFifoReaderService started")

    async def stop(self) -> None:
        """Stop the FIFO reader task."""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("AudioFifoReaderService stopped")

    async def _read_fifo_loop(self) -> None:
        """Read from FIFO and stream to WebSocket clients in a continuous loop."""
        fifo_fd = None
        try:
            # Open FIFO in non-blocking mode
            fifo_fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            logger.info("Opened FIFO for reading: %s", self.fifo_path)

            while self.running:
                try:
                    buffer_size = 4096  # Must match producer's write size
                    audio_data_bytes = os.read(fifo_fd, buffer_size)

                    if audio_data_bytes:
                        # Stream to WebSocket clients
                        await self.audio_websocket_service.stream_audio_chunk(audio_data_bytes)
                        # Also send to spectrogram service if available
                        if self.spectrogram_service:
                            await self.spectrogram_service.process_audio_chunk(audio_data_bytes)
                    else:
                        # No data available, sleep to avoid busy waiting
                        await asyncio.sleep(0.01)

                except BlockingIOError:
                    # FIFO would block, no data available
                    await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error(
                        "Error reading from FIFO or streaming to WebSocket: %s", e, exc_info=True
                    )
                    await asyncio.sleep(0.1)  # Brief pause before retrying

        except FileNotFoundError:
            logger.error(
                "FIFO not found at %s. Ensure audio_capture is running and creating it.",
                self.fifo_path,
            )
        except Exception as e:
            logger.error("Error in FIFO reader loop: %s", e, exc_info=True)
        finally:
            if fifo_fd is not None:
                os.close(fifo_fd)
                logger.info("Closed FIFO: %s", self.fifo_path)
