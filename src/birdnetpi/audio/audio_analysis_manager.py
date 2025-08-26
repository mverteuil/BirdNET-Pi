import asyncio
import datetime
import logging
import threading
import time
from collections import deque
from datetime import UTC
from typing import TYPE_CHECKING, Any

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.bird_detection_service import BirdDetectionService
from birdnetpi.species.parser import SpeciesComponents, SpeciesParser
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver

if TYPE_CHECKING:
    from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService

logger = logging.getLogger(__name__)


class AudioAnalysisManager:
    """Manager for orchestrating audio data analysis workflows."""

    def __init__(
        self,
        file_manager: FileManager,
        path_resolver: PathResolver,
        config: BirdNETConfig,
        multilingual_service: "MultilingualDatabaseService",
        session: "AsyncSession",
        detection_buffer_max_size: int = 1000,
        buffer_flush_interval: float = 5.0,
    ) -> None:
        logger.info("AudioAnalysisManager initialized.")
        self.file_manager = file_manager
        self.path_resolver = path_resolver
        self.config = config
        self.analysis_client = BirdDetectionService(config)

        # Initialize SpeciesParser with multilingual database service for canonical name lookups
        self.species_parser = SpeciesParser(multilingual_service)
        # Set the session for database queries
        SpeciesParser.set_session(session)

        # Buffer for accumulating audio chunks for analysis
        self.audio_buffer = np.array([], dtype=np.int16)
        self.buffer_size_samples = int(3.0 * config.sample_rate)  # 3 seconds of audio

        # In-memory buffer for detection events when FastAPI is unavailable
        self.detection_buffer: deque[dict[str, Any]] = deque(maxlen=detection_buffer_max_size)
        self.buffer_lock = threading.Lock()
        self.flush_interval = buffer_flush_interval

        # Initialize background buffer flush task (but don't start it yet)
        self._stop_flush_task = False
        self._flush_task = None
        # Thread will be started by calling start_buffer_flush_task()

    def start_buffer_flush_task(self) -> None:
        """Start the background task to flush detection buffer."""
        if self._flush_task and self._flush_task.is_alive():
            logger.warning("Buffer flush task already running")
            return
        self._start_buffer_flush_task()

    def _start_buffer_flush_task(self) -> None:
        """Start the background task to flush detection buffer."""

        def flush_loop() -> None:
            while not self._stop_flush_task:
                try:
                    asyncio.run(self._flush_detection_buffer())
                except Exception:
                    logger.exception("Error in buffer flush loop")
                time.sleep(self.flush_interval)

        flush_thread = threading.Thread(target=flush_loop, daemon=True)
        flush_thread.start()
        self._flush_task = flush_thread

    async def _flush_detection_buffer(self) -> None:
        """Attempt to flush buffered detection events to FastAPI."""
        if not self.detection_buffer:
            return

        # Copy and clear buffer atomically
        with self.buffer_lock:
            buffered_detections = list(self.detection_buffer)
            self.detection_buffer.clear()

        if not buffered_detections:
            return

        logger.info(
            "Attempting to flush buffered detections", extra={"count": len(buffered_detections)}
        )

        # Try to send each buffered detection
        successful_sends = 0
        failed_detections = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for detection_data in buffered_detections:
                try:
                    response = await client.post(
                        "http://127.0.0.1:8000/api/detections", json=detection_data
                    )
                    response.raise_for_status()
                    successful_sends += 1
                    species_name = detection_data.get("species_tensor", "Unknown")
                    logger.debug(
                        "Successfully flushed buffered detection", extra={"species": species_name}
                    )
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    logger.debug(
                        "Failed to flush detection (will re-buffer)",
                        extra={"error": str(e), "detection": detection_data},
                    )
                    failed_detections.append(detection_data)
                except Exception:
                    logger.exception(
                        "Unexpected error flushing detection", extra={"detection": detection_data}
                    )
                    failed_detections.append(detection_data)

        # Re-add failed detections to buffer
        if failed_detections:
            with self.buffer_lock:
                for detection in failed_detections:
                    self.detection_buffer.append(detection)
            logger.warning(
                "Re-buffered failed detections",
                extra={"count": len(failed_detections), "failed_detections": failed_detections},
            )

        if successful_sends > 0:
            logger.info(
                "Successfully flushed buffered detections", extra={"count": successful_sends}
            )

    def stop_buffer_flush_task(self) -> None:
        """Stop the background buffer flush task."""
        self._stop_flush_task = True
        if self._flush_task and self._flush_task.is_alive():
            self._flush_task.join(timeout=5.0)

    async def process_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Process a chunk of audio data for analysis."""
        # Convert bytes to numpy array (assuming int16 from AudioCaptureService)
        audio_data = np.frombuffer(audio_data_bytes, dtype=np.int16)
        logger.debug("AudioAnalysisService received chunk", extra={"shape": audio_data.shape})

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
            current_week = datetime.datetime.now(UTC).isocalendar()[1]

            # Perform BirdNET analysis
            results = self.analysis_client.get_analysis_results(
                audio_chunk=audio_chunk,
                latitude=self.config.latitude,
                longitude=self.config.longitude,
                week=current_week,
                sensitivity=self.config.sensitivity_setting,
            )

            # Process results and send detection events for confident detections
            for species_tensor, confidence in results:
                if confidence >= self.config.species_confidence_threshold:
                    # Parse species tensor using SpeciesParser
                    try:
                        species_components = await SpeciesParser.parse_tensor_species(
                            species_tensor
                        )
                    except ValueError as e:
                        logger.error(
                            "Invalid species tensor format",
                            extra={"species_tensor": species_tensor, "error": str(e)},
                        )
                        continue  # Skip this detection if tensor format is invalid
                    # Convert audio chunk back to bytes for saving
                    audio_bytes = (audio_chunk * 32767).astype(np.int16).tobytes()
                    await self._send_detection_event(species_components, confidence, audio_bytes)
                    logger.info(
                        f"Bird detected: {species_components.scientific_name} "
                        f"(confidence: {confidence:.3f})"
                    )

        except Exception:
            logger.exception("Error during BirdNET analysis")

    async def _send_detection_event(
        self, species_components: SpeciesComponents, confidence: float, raw_audio_bytes: bytes
    ) -> None:
        """Send a detection event to the FastAPI application.

        Args:
            species_components: Parsed species components from SpeciesParser
            confidence: Detection confidence score
            raw_audio_bytes: Raw audio data bytes
        """
        # Get relative path for the audio file
        timestamp = datetime.datetime.now(UTC)
        current_week = timestamp.isocalendar()[1]
        audio_file_path = self.path_resolver.get_detection_audio_path(
            species_components.scientific_name, timestamp
        )

        # Save raw audio to disk using FileManager
        try:
            audio_file_instance = self.file_manager.save_detection_audio(
                audio_file_path,
                np.frombuffer(  # type: ignore[arg-type]
                    raw_audio_bytes, dtype=np.int16
                ),  # Ensure raw_audio_bytes is int16 numpy array
                self.config.sample_rate,  # Get from config
                self.config.audio_channels,  # Get from config
            )
            logger.info(
                "Saved detection audio", extra={"file_path": str(audio_file_instance.file_path)}
            )
        except Exception:
            logger.exception("Failed to save detection audio")
            return  # Don't send detection if audio save fails

        detection_data = {
            "species_tensor": species_components.scientific_name
            + "_"
            + species_components.common_name,
            "scientific_name": species_components.scientific_name,
            "common_name": species_components.common_name,
            "confidence": confidence,
            "timestamp": timestamp.isoformat(),  # Use the same timestamp for consistency
            "audio_file_path": str(
                audio_file_instance.file_path
            ),  # Convert Path to string for JSON serialization
            "duration": audio_file_instance.duration,
            "size_bytes": audio_file_instance.size_bytes,
            "spectrogram_path": None,
            "latitude": self.config.latitude,
            "longitude": self.config.longitude,
            "species_confidence_threshold": self.config.species_confidence_threshold,
            "week": current_week,
            "sensitivity_setting": self.config.sensitivity_setting,
            "overlap": 0.5,  # Fixed overlap from buffer processing
        }
        # Try to send detection event to FastAPI
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # FastAPI is assumed to be on the same Docker network
                # and accessible via its service name
                response = await client.post(
                    "http://fastapi:8888/api/detections", json=detection_data
                )
                response.raise_for_status()  # Raise an exception for bad status codes
                logger.info(
                    "Detection event sent", extra={"species": species_components.scientific_name}
                )
                return  # Success - no need to buffer
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(
                "FastAPI unavailable, buffering detection",
                extra={"error": str(e), "detection_buffered": True},
            )
        except Exception as e:
            logger.warning(
                "Unexpected error sending detection, buffering",
                extra={"error": str(e), "detection_buffered": True},
            )

        # FastAPI is unavailable - buffer the detection
        with self.buffer_lock:
            self.detection_buffer.append(detection_data)
            buffer_size = len(self.detection_buffer)

        logger.info(
            f"Buffered detection event for {species_components.scientific_name} "
            f"(buffer size: {buffer_size})"
        )
