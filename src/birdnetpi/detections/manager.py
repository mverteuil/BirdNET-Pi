"""Single source of truth for all detection data access.

This manager provides a unified interface for accessing detection data,
coordinating between the database service, multilingual service, and
species display service. It acts as a facade to simplify data access
patterns while preserving the underlying service architecture.
"""

import base64
import functools
import logging
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import (
    AudioFile,
    Detection,
    DetectionBase,
)
from birdnetpi.detections.queries import (
    DetectionQueryService,
)
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.models.detections import DetectionEvent

logger = logging.getLogger(__name__)

# Type variable for decorator
T = TypeVar("T")


def emit_detection_event(func: Callable[..., Any]) -> Callable[..., Any]:
    """Emit detection events after successful data operations.

    This decorator automatically emits a Blinker signal when a Detection
    is successfully created or modified. It replaces the need for a separate
    DetectionManager by handling event emission at the point of data modification.

    Args:
        func: A method that returns a Detection object

    Returns:
        Wrapped function that emits events after successful execution
    """

    @functools.wraps(func)
    async def wrapper(self: "DataManager", *args: Any, **kwargs: Any) -> Detection:  # noqa: ANN401
        # Execute the original function
        detection = await func(self, *args, **kwargs)

        # Emit the detection event if we have a valid detection
        if detection and isinstance(detection, Detection):
            logger.info(f"Emitting detection signal for {detection.id}")
            detection_signal.send(self, detection=detection)

        return detection

    return wrapper


class DataManager:
    """Single source of truth for all detection data access.

    This manager coordinates between various services to provide a unified
    API for detection data access. It does not absorb the services but
    acts as a facade to simplify access patterns.
    """

    def __init__(
        self,
        database_service: CoreDatabaseService,
        species_database: SpeciesDatabaseService,
        species_display_service: SpeciesDisplayService,
        file_manager: FileManager,
        path_resolver: PathResolver,
        detection_query_service: DetectionQueryService | None = None,
    ) -> None:
        """Initialize the DataManager with required services.

        Args:
            database_service: Core database service for BirdNET-Pi data
            species_database: Handles IOC, Avibase, PatLevin databases
            species_display_service: Complex display logic for species names
            file_manager: Handles file operations for audio and spectrograms
            path_resolver: Resolves paths for detection files
            detection_query_service: Legacy service for compatibility (will be absorbed)
        """
        self.database_service = database_service
        self.multilingual = species_database
        self.species_display = species_display_service
        self.file_manager = file_manager
        self.path_resolver = path_resolver
        self.query_service = detection_query_service

    # ==================== Core CRUD Operations ====================

    async def get_detection_by_id(self, detection_id: int) -> Detection | None:
        """Get a single detection by its ID."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(Detection).where(Detection.id == detection_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error retrieving detection by ID")
                raise

    async def get_all_detections(
        self, limit: int | None = None, offset: int | None = None
    ) -> Sequence[DetectionBase]:
        """Get all detections with optional pagination."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(Detection)
                if offset:
                    stmt = stmt.offset(offset)
                if limit:
                    stmt = stmt.limit(limit)
                result = await session.execute(stmt)
                return list(result.scalars())
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error retrieving all detections")
                raise

    @emit_detection_event
    async def create_detection(self, detection_event: DetectionEvent) -> Detection:
        """Create a new detection record from a DetectionEvent.

        This method handles both audio file saving and database persistence.
        It creates a detection in the database and automatically emits a
        detection event via the @emit_detection_event decorator.
        """
        async with self.database_service.get_async_db() as session:
            try:
                # Decode and save audio data if provided
                audio_file = None
                if detection_event.audio_data:
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(detection_event.audio_data)

                    # Get the file path for this detection
                    audio_file_path = self.path_resolver.get_detection_audio_path(
                        detection_event.scientific_name, detection_event.timestamp
                    )

                    # Save audio file (convert numpy array back to bytes)
                    audio_file_instance = self.file_manager.save_detection_audio(
                        audio_file_path,
                        audio_bytes,  # Use the decoded bytes directly
                        detection_event.sample_rate,
                        detection_event.channels,
                    )

                    # Create AudioFile record
                    audio_file = AudioFile(
                        file_path=audio_file_instance.file_path,
                        duration=audio_file_instance.duration,
                        size_bytes=audio_file_instance.size_bytes,
                    )
                    session.add(audio_file)
                    await session.flush()

                    logger.info(
                        "Saved detection audio",
                        extra={"file_path": str(audio_file_instance.file_path)},
                    )

                # Create Detection
                # Calculate hour_epoch for optimized weather JOINs
                hour_epoch = (
                    int(detection_event.timestamp.timestamp() / 3600)
                    if detection_event.timestamp
                    else None
                )

                detection = Detection(
                    species_tensor=detection_event.species_tensor,
                    scientific_name=detection_event.scientific_name,
                    common_name=detection_event.common_name,
                    confidence=detection_event.confidence,
                    timestamp=detection_event.timestamp,
                    audio_file_id=audio_file.id if audio_file else None,
                    latitude=detection_event.latitude,
                    longitude=detection_event.longitude,
                    species_confidence_threshold=detection_event.species_confidence_threshold,
                    week=detection_event.week,
                    sensitivity_setting=detection_event.sensitivity_setting,
                    overlap=detection_event.overlap,
                    hour_epoch=hour_epoch,
                )
                session.add(detection)
                await session.commit()
                await session.refresh(detection)
                return detection
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error creating detection")
                raise

    async def update_detection(
        self, detection_id: int, updates: dict[str, Any]
    ) -> Detection | None:
        """Update a detection record."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(Detection).where(Detection.id == detection_id)
                result = await session.execute(stmt)
                detection = result.scalar_one_or_none()
                if detection:
                    for key, value in updates.items():
                        if hasattr(detection, key):
                            setattr(detection, key, value)
                    await session.commit()
                    await session.refresh(detection)
                return detection
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error updating detection")
                raise

    async def delete_detection(self, detection_id: int) -> bool:
        """Delete a detection record."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(Detection).where(Detection.id == detection_id)
                result = await session.execute(stmt)
                detection = result.scalar_one_or_none()
                if detection:
                    _ = session.delete(detection)
                    await session.commit()
                    return True
                return False
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error deleting detection")
                raise

    # ==================== Query Methods ====================
    # NOTE: Query methods have been moved to DetectionQueryService.
    # Use DetectionQueryService directly for all query operations.

    # ==================== Translation Helpers ====================
    # NOTE: Translation helper methods have been moved to DetectionQueryService.
    # Use DetectionQueryService directly for display name formatting.

    # ==================== AudioFile Operations ====================

    async def get_audio_file_by_path(self, file_path: str) -> AudioFile | None:
        """Get an audio file record by its path."""
        async with self.database_service.get_async_db() as session:
            try:
                result = await session.scalar(
                    select(AudioFile).where(AudioFile.file_path == file_path)
                )
                return result
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error retrieving audio file")
                raise
