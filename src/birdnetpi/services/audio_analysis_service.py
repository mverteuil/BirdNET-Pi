import datetime
import logging

import httpx
import numpy as np

from birdnetpi.managers.file_manager import FileManager
from birdnetpi.models.config import BirdNETConfig
from birdnetpi.services.bird_detection_service import BirdDetectionService
from birdnetpi.utils.file_path_resolver import FilePathResolver

logger = logging.getLogger(__name__)


class AudioAnalysisService:
    """Service for processing audio data for analysis."""

    def __init__(
        self,
        file_manager: FileManager,
        file_path_resolver: FilePathResolver,
        config: BirdNETConfig,
    ) -> None:
        logger.info("AudioAnalysisService initialized.")
        self.file_manager = file_manager
        self.file_path_resolver = file_path_resolver
        self.config = config
        self.analysis_client = BirdDetectionService(config)

        # Buffer for accumulating audio chunks for analysis
        self.audio_buffer = np.array([], dtype=np.int16)
        self.buffer_size_samples = int(3.0 * config.sample_rate)  # 3 seconds of audio

    async def process_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Process a chunk of audio data for analysis."""
        # Convert bytes to numpy array (assuming int16 from AudioCaptureService)
        audio_data = np.frombuffer(audio_data_bytes, dtype=np.int16)
        logger.debug(f"AudioAnalysisService received chunk. Shape: {audio_data.shape}")

        # Audio streaming is now handled by separate WebSocket daemon via livestream.fifo

        # Accumulate audio data in buffer
        self.audio_buffer = np.concatenate([self.audio_buffer, audio_data])

        # Process when we have enough audio (3 seconds worth)
        if len(self.audio_buffer) >= self.buffer_size_samples:
            # Take the first 3 seconds for analysis
            analysis_chunk = self.audio_buffer[: self.buffer_size_samples]

            # Remove processed samples from buffer (keep overlap for continuity)
            overlap_samples = int(0.5 * self.config.sample_rate)  # 0.5 second overlap
            self.audio_buffer = self.audio_buffer[self.buffer_size_samples - overlap_samples :]

            # Convert int16 to float32 and normalize for BirdNET analysis
            audio_float = analysis_chunk.astype(np.float32) / 32768.0

            # Perform BirdNET analysis
            await self._analyze_audio_chunk(audio_float)

    async def _analyze_audio_chunk(self, audio_chunk: np.ndarray) -> None:
        """Analyze an audio chunk using BirdNET and send detection events."""
        try:
            # Get current week for species filtering
            current_week = datetime.datetime.now().isocalendar()[1]

            # Perform BirdNET analysis
            results = self.analysis_client.get_analysis_results(
                audio_chunk=audio_chunk,
                lat=self.config.latitude,
                lon=self.config.longitude,
                week=current_week,
                sensitivity=self.config.sensitivity,
            )

            # Process results and send detection events for confident detections
            for species, confidence in results:
                if confidence >= self.config.confidence:
                    # Convert audio chunk back to bytes for saving
                    audio_bytes = (audio_chunk * 32767).astype(np.int16).tobytes()
                    await self._send_detection_event(species, confidence, audio_bytes)
                    logger.info(f"Bird detected: {species} (confidence: {confidence:.3f})")

        except Exception as e:
            logger.error(f"Error during BirdNET analysis: {e}", exc_info=True)

    async def _send_detection_event(
        self, species: str, confidence: float, raw_audio_bytes: bytes
    ) -> None:
        """Send a detection event to the FastAPI application."""
        # Get relative path for the audio file
        timestamp = datetime.datetime.now()
        current_week = timestamp.isocalendar()[1]
        relative_audio_file_path = self.file_path_resolver.get_detection_audio_path(
            species, timestamp
        )

        # Save raw audio to disk using FileManager
        try:
            audio_file_instance = self.file_manager.save_detection_audio(
                relative_audio_file_path,
                np.frombuffer(  # type: ignore[arg-type]
                    raw_audio_bytes, dtype=np.int16
                ),  # Ensure raw_audio_bytes is int16 numpy array
                self.config.sample_rate,  # Get from config
                self.config.audio_channels,  # Get from config
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
            "spectrogram_path": None,
            "latitude": self.config.latitude,
            "longitude": self.config.longitude,
            "species_confidence_threshold": self.config.confidence,
            "week": current_week,
            "sensitivity_setting": self.config.sensitivity,
            "overlap": 0.5,  # Fixed overlap from buffer processing
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
