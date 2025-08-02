import logging
import os

import numpy as np
import sounddevice as sd

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.filters import FilterChain

logger = logging.getLogger(__name__)


class AudioCaptureService:
    """Manages audio capture from a specified input device using sounddevice."""

    def __init__(
        self,
        config: BirdNETConfig,
        analysis_fifo_fd: int,
        livestream_fifo_fd: int,
        analysis_filter_chain: FilterChain | None = None,
        livestream_filter_chain: FilterChain | None = None,
    ) -> None:
        """Initialize the AudioCaptureService.

        Args:
            config: BirdNET configuration
            analysis_fifo_fd: File descriptor for analysis FIFO
            livestream_fifo_fd: File descriptor for livestream FIFO
            analysis_filter_chain: Optional filter chain for analysis pipeline
            livestream_filter_chain: Optional filter chain for livestream pipeline
        """
        self.config = config
        self.analysis_fifo_fd = analysis_fifo_fd
        self.livestream_fifo_fd = livestream_fifo_fd
        self.analysis_filter_chain = analysis_filter_chain
        self.livestream_filter_chain = livestream_filter_chain
        self.stream = None

        # Configure filter chains if provided
        if self.analysis_filter_chain:
            self.analysis_filter_chain.configure(config.sample_rate, config.audio_channels)
            logger.info(
                "Analysis filter chain configured with %d filters", len(self.analysis_filter_chain)
            )

        if self.livestream_filter_chain:
            self.livestream_filter_chain.configure(config.sample_rate, config.audio_channels)
            logger.info(
                "Livestream filter chain configured with %d filters",
                len(self.livestream_filter_chain),
            )

        logger.info("AudioCaptureService initialized.")

    def _callback(
        self, indata: np.ndarray, frames: int, time: sd.CallbackStop, status: sd.CallbackFlags
    ) -> None:
        """Process a block of audio data from the sounddevice stream."""
        if status:
            logger.warning("Audio stream status: %s", status)

        # Convert float32 to int16 for processing
        audio_int16 = (indata * 32767).astype(np.int16)

        # Apply analysis filter chain if configured
        analysis_audio = audio_int16
        if self.analysis_filter_chain:
            analysis_audio = self.analysis_filter_chain.process(audio_int16)

        # Apply livestream filter chain if configured
        livestream_audio = audio_int16
        if self.livestream_filter_chain:
            livestream_audio = self.livestream_filter_chain.process(audio_int16)

        # Convert filtered audio to bytes for FIFO writing
        analysis_bytes = analysis_audio.tobytes()
        livestream_bytes = livestream_audio.tobytes()

        # Write filtered audio to respective FIFOs
        try:
            os.write(self.analysis_fifo_fd, analysis_bytes)
            os.write(self.livestream_fifo_fd, livestream_bytes)
        except BlockingIOError:
            # This can happen if the readers are not keeping up
            logger.warning("FIFO write would block, skipping frame.")
        except Exception as e:
            logger.error("Error writing to FIFO: %s", e)

    def start_capture(self) -> None:
        """Start the audio capture stream."""
        try:
            device_id = self.config.audio_device_index
            samplerate = self.config.sample_rate
            channels = self.config.audio_channels

            logger.info(
                "Attempting to start audio capture on device ID: %s, samplerate: %s, channels: %s",
                device_id,
                samplerate,
                channels,
            )

            self.stream = sd.InputStream(
                device=device_id, samplerate=samplerate, channels=channels, callback=self._callback
            )
            self.stream.start()
            logger.info("Audio capture stream started.")
        except Exception as e:
            logger.error("Failed to start audio capture stream: %s", e)
            raise

    def stop_capture(self) -> None:
        """Stop the audio capture stream."""
        if self.stream and not self.stream.stopped:
            self.stream.stop()
            self.stream.close()
            logger.info("Audio capture stream stopped and closed.")
        else:
            logger.info("Audio capture stream is not running.")
