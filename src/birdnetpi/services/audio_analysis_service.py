import asyncio
import datetime
import logging
import threading
import time
from collections import deque
from typing import Any

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
        detection_buffer_max_size: int = 1000,
        buffer_flush_interval: float = 5.0,
    ) -> None:
        logger.info("AudioAnalysisService initialized.")
        self.file_manager = file_manager
        self.file_path_resolver = file_path_resolver
        self.config = config
        self.analysis_client = BirdDetectionService(config)

        # Buffer for accumulating audio chunks for analysis
        self.audio_buffer = np.array([], dtype=np.int16)
        self.buffer_size_samples = int(3.0 * config.sample_rate)  # 3 seconds of audio

        # In-memory buffer for detection events when FastAPI is unavailable
        self.detection_buffer: deque[dict[str, Any]] = deque(maxlen=detection_buffer_max_size)
        self.buffer_lock = threading.Lock()
        self.flush_interval = buffer_flush_interval

        # Start background buffer flush task
        self._stop_flush_task = False
        self._flush_task = None
        self._start_buffer_flush_task()

    def _start_buffer_flush_task(self) -> None:
        """Start the background task to flush detection buffer."""

        def flush_loop():
            while not self._stop_flush_task:
                try:
                    asyncio.run(self._flush_detection_buffer())
                except Exception as e:
                    logger.error(f"Error in buffer flush loop: {e}", exc_info=True)
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

        logger.info(f"Attempting to flush {len(buffered_detections)} buffered detections")

        # Try to send each buffered detection
        successful_sends = 0
        failed_detections = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for detection_data in buffered_detections:
                try:
                    response = await client.post(
                        "http://fastapi:8888/api/detections", json=detection_data
                    )
                    response.raise_for_status()
                    successful_sends += 1
                    logger.debug(
                        f"Successfully flushed buffered detection: {detection_data['species']}"
                    )
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    logger.debug(f"Failed to flush detection (will re-buffer): {e}")
                    failed_detections.append(detection_data)
                except Exception as e:
                    logger.error(f"Unexpected error flushing detection: {e}", exc_info=True)
                    failed_detections.append(detection_data)

        # Re-add failed detections to buffer
        if failed_detections:
            with self.buffer_lock:
                for detection in failed_detections:
                    self.detection_buffer.append(detection)
            logger.warning(f"Re-buffered {len(failed_detections)} failed detections")

        if successful_sends > 0:
            logger.info(f"Successfully flushed {successful_sends} buffered detections")

    def stop_buffer_flush_task(self) -> None:
        """Stop the background buffer flush task."""
        self._stop_flush_task = True
        if self._flush_task and self._flush_task.is_alive():
            self._flush_task.join(timeout=5.0)

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
                sensitivity=self.config.sensitivity_setting,
            )

            # Process results and send detection events for confident detections
            for species, confidence in results:
                if confidence >= self.config.species_confidence_threshold:
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
                logger.info(f"Detection event sent: {detection_data['species']}")
                return  # Success - no need to buffer
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"FastAPI unavailable, buffering detection: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error sending detection, buffering: {e}")

        # FastAPI is unavailable - buffer the detection
        with self.buffer_lock:
            self.detection_buffer.append(detection_data)
            buffer_size = len(self.detection_buffer)

        logger.info(
            f"Buffered detection event for {detection_data['species']} (buffer size: {buffer_size})"
        )
