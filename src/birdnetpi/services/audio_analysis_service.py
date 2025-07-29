import datetime
import logging

import httpx
import numpy as np

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.file_path_resolver import FilePathResolver

logger = logging.getLogger(__name__)


class AudioAnalysisService:
    """Service for processing audio data for analysis."""

    def __init__(
        self, file_manager: FileManager, file_path_resolver: FilePathResolver, config: BirdNETConfig
    ) -> None:
        logger.info("AudioAnalysisService initialized.")
        self.detection_counter = 0  # For simulating detections
        self.file_manager = file_manager
        self.file_path_resolver = file_path_resolver
        self.config = config

    async def process_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Process a chunk of audio data for analysis."""
        # Convert bytes to numpy array (assuming int16 from AudioCaptureService)
        audio_data = np.frombuffer(audio_data_bytes, dtype=np.int16)
        logger.debug(f"AudioAnalysisService received chunk. Shape: {audio_data.shape}")

        # TODO: Replace with actual BirdNET-Lite analysis
        # Simulate a detection every N chunks for testing
        self.detection_counter += 1
        if self.detection_counter % 100 == 0:  # Simulate a detection every 100 chunks
            await self._send_detection_event("Simulated Bird", 0.95, audio_data_bytes)

    async def _send_detection_event(
        self, species: str, confidence: float, raw_audio_bytes: bytes
    ) -> None:
        """Send a detection event to the FastAPI application."""
        # Get relative path for the audio file
        timestamp = datetime.datetime.now()
        relative_audio_file_path = self.file_path_resolver.get_detection_audio_path(
            species, timestamp
        )

        # Save raw audio to disk using FileManager
        try:
            audio_file_instance = self.file_manager.save_detection_audio(
                relative_audio_file_path,
                np.frombuffer(
                    raw_audio_bytes, dtype=np.int16
                ),  # Ensure raw_audio_bytes is int16 numpy array
                self.config.sample_rate,  # Get from config
                self.config.audio_channels,  # Get from config
                timestamp,  # Pass recording_start_time
            )
            logger.info(f"Saved detection audio to {audio_file_instance.file_path}")
        except Exception as e:
            logger.error(f"Failed to save detection audio: {e}", exc_info=True)
            return  # Don't send detection if audio save fails

        detection_data = {
            "species": species,
            "confidence": confidence,
            "timestamp": timestamp.isoformat(),  # Use the same timestamp for consistency
            "audio_file_path": audio_file_instance.file_path,
            "duration": audio_file_instance.duration,
            "size_bytes": audio_file_instance.size_bytes,
            "recording_start_time": audio_file_instance.recording_start_time.isoformat(),
            "spectrogram_path": None,
            "latitude": None,
            "longitude": None,
            "cutoff": None,
            "week": None,
            "sensitivity": None,
            "overlap": None,
            "is_extracted": False,
        }
        try:
            async with httpx.AsyncClient() as client:
                # FastAPI is assumed to be on the same Docker network
                # and accessible via its service name
                response = await client.post(
                    "http://fastapi:8888/api/detections", json=detection_data
                )
                response.raise_for_status()  # Raise an exception for bad status codes
                logger.info(f"Detection event sent: {detection_data}")
        except httpx.RequestError as e:
            logger.error(f"Error sending detection event: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(
                "Error response %s while sending detection event: %s",
                e.response.status_code,
                e.response.text,
            )
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while sending detection event: {e}", exc_info=True
            )
