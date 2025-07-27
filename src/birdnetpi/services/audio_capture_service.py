import logging
import sounddevice as sd
import numpy as np
from multiprocessing import Queue

from birdnetpi.models.birdnet_config import BirdNETConfig

logger = logging.getLogger(__name__)

class AudioCaptureService:
    """
    Manages audio capture from a specified input device using sounddevice.
    """

    def __init__(self, config: BirdNETConfig, audio_queue: Queue) -> None:
        """
        Initializes the AudioCaptureService.

        Args:
            config (BirdNETConfig): The application configuration.
            audio_queue (Queue): The multiprocessing queue to put audio data into.
        """
        self.config = config
        self.audio_queue = audio_queue
        self.stream = None
        logger.info("AudioCaptureService initialized.")

    def _callback(self, indata, frames, time, status):
        """
        Callback function for the sounddevice stream.
        This function is executed for every block of audio data.
        """
        if status:
            logger.warning(f"Audio stream status: {status}")
        # For now, just print the shape of the incoming data
        logger.info(f"Audio data shape: {indata.shape}")

    def start_capture(self) -> None:
        """
        Starts the audio capture stream.
        """
        try:
            device_id = self.config.audio_device_index
            samplerate = self.config.sample_rate
            channels = self.config.audio_channels

            logger.info(f"Attempting to start audio capture on device ID: {device_id} with samplerate: {samplerate}, channels: {channels}")

            self.stream = sd.InputStream(
                device=device_id,
                samplerate=samplerate,
                channels=channels,
                callback=self._callback
            )
            self.stream.start()
            logger.info("Audio capture stream started.")
        except Exception as e:
            logger.error(f"Failed to start audio capture stream: {e}")
            raise

    def stop_capture(self) -> None:
        """
        Stops the audio capture stream.
        """
        if self.stream and self.stream.running:
            self.stream.stop()
            self.stream.close()
            logger.info("Audio capture stream stopped and closed.")
        else:
            logger.info("Audio capture stream is not running.")
