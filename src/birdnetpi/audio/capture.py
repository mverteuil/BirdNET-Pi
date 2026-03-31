import logging
import os

import numpy as np
import sounddevice as sd

from birdnetpi.audio.devices import AudioDeviceService
from birdnetpi.audio.filters import FilterChain
from birdnetpi.config import BirdNETConfig

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
        self._shutdown_requested = False
        self.device_sample_rate = None  # Will be determined from device
        self.audio_device_service = AudioDeviceService()

        # Filter chains configured after determining device sample rate
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
        except BrokenPipeError:
            # This happens during shutdown when FIFOs are closed
            logger.debug("FIFO closed, requesting shutdown.")
            # Don't stop the stream from within the callback - just flag for shutdown
            self._shutdown_requested = True
        except OSError as e:
            # Handle other OS errors gracefully during shutdown
            if e.errno == 9:  # Bad file descriptor (EBADF)
                logger.debug("FIFO file descriptor closed during shutdown.")
                self._shutdown_requested = True
            else:
                logger.error("Error writing to FIFO: %s", e)

    def start_capture(self) -> None:
        """Start the audio capture stream."""
        try:
            # sounddevice expects None for default device, not -1
            device_id = self.config.audio_device_index
            if device_id == -1:
                device_id = None
            channels = self.config.audio_channels
            target_sample_rate = self.config.sample_rate  # What BirdNET expects (48000)

            # Let sounddevice/PortAudio handle sample rate conversion automatically
            # This works on all platforms (macOS, Linux, Windows) though quality may vary:
            # - macOS: CoreAudio provides high-quality resampling
            # - Linux/ALSA: Basic resampling (usually linear or speex)
            # - Linux/PulseAudio: Better quality resampling
            # - Works well enough for bird detection on Raspberry Pi and other SBCs
            logger.info(
                "Using sounddevice automatic resampling (PortAudio) - requesting %dHz",
                target_sample_rate,
            )

            # Store the target sample rate (what we request from sounddevice)
            self.device_sample_rate = target_sample_rate

            if self.analysis_filter_chain is not None:
                # Configure the chain with target sample rate
                self.analysis_filter_chain.configure(target_sample_rate, channels)
                logger.info(
                    "Analysis filter chain configured with %d filters",
                    len(self.analysis_filter_chain),
                )

            if self.livestream_filter_chain is not None:
                # Configure livestream chain with target sample rate
                self.livestream_filter_chain.configure(target_sample_rate, channels)
                logger.info(
                    "Livestream filter chain configured with %d filters",
                    len(self.livestream_filter_chain),
                )

            logger.info(
                "Starting audio capture on device ID: %s, sample rate: %dHz, channels: %s",
                device_id,
                target_sample_rate,
                channels,
            )

            self.stream = sd.InputStream(
                device=device_id,
                samplerate=target_sample_rate,  # Request target rate, let sounddevice resample
                channels=channels,
                callback=self._callback,
            )
            self.stream.start()
            logger.info("Audio capture stream started at %dHz.", target_sample_rate)
        except Exception as e:
            logger.error("Failed to start audio capture stream: %s", e)
            raise

    def stop_capture(self) -> None:
        """Stop the audio capture stream gracefully."""
        if self.stream and not self.stream.stopped:
            try:
                # Abort first to immediately stop processing
                self.stream.abort()
                # Small delay to allow threads to terminate
                import time

                time.sleep(0.1)
                # Then close the stream
                self.stream.close()
                logger.info("Audio capture stream stopped and closed.")
            except Exception as e:
                # pthread_join errors during shutdown are expected and can be ignored
                error_str = str(e)
                if "pthread_join" in error_str or "PaUnixThread_Terminate" in error_str:
                    logger.debug("Thread termination warning during shutdown (expected): %s", e)
                else:
                    logger.error(f"Error stopping audio stream: {e}")
        else:
            logger.info("Audio capture stream is not running.")
