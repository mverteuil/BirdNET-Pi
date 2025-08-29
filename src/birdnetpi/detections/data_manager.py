"""Single source of truth for all detection data access.

This manager provides a unified interface for accessing detection data,
coordinating between the database service, multilingual service, and
species display service. It acts as a facade to simplify data access
patterns while preserving the underlying service architecture.
"""

import base64
import datetime
import functools
import logging
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, TypeVar

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.detection_query_service import (
    DetectionQueryService,
)
from birdnetpi.detections.models import (
    AudioFile,
    Detection,
    DetectionBase,
    DetectionWithLocalization,
)
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
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
        database_service: DatabaseService,
        multilingual_service: MultilingualDatabaseService,
        species_display_service: SpeciesDisplayService,
        file_manager: FileManager,
        path_resolver: PathResolver,
        detection_query_service: DetectionQueryService | None = None,
    ) -> None:
        """Initialize the DataManager with required services.

        Args:
            database_service: Core database service for BirdNET-Pi data
            multilingual_service: Handles IOC, Avibase, PatLevin databases
            species_display_service: Complex display logic for species names
            file_manager: Handles file operations for audio and spectrograms
            path_resolver: Resolves paths for detection files
            detection_query_service: Legacy service for compatibility (will be absorbed)
        """
        self.database_service = database_service
        self.multilingual = multilingual_service
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

    async def query_detections(
        self,
        species: str | list[str] | None = None,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str = "timestamp",
        order_desc: bool = True,
        include_localization: bool = False,
        language_code: str = "en",
    ) -> Sequence[DetectionBase] | list[DetectionWithLocalization]:
        """Query detections with flexible filtering and optional localization.

        All queries are delegated to DetectionQueryService for consistency.
        """
        if not self.query_service:
            raise RuntimeError("DetectionQueryService not available")

        # Always use DetectionQueryService for all queries
        return await self.query_service.query_detections(
            species=species,
            start_date=start_date,
            end_date=end_date,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
            include_localization=include_localization,
            language_code=language_code,
        )

    # ==================== Count Methods ====================

    async def count_detections(self, filters: dict[str, Any] | None = None) -> int:
        """Count detections with optional filters."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(func.count(Detection.id))

                if filters:
                    if "species" in filters:
                        stmt = stmt.where(Detection.scientific_name == filters["species"])
                    if "start_date" in filters:
                        stmt = stmt.where(Detection.timestamp >= filters["start_date"])
                    if "end_date" in filters:
                        stmt = stmt.where(Detection.timestamp <= filters["end_date"])
                    if "min_confidence" in filters:
                        stmt = stmt.where(Detection.confidence >= filters["min_confidence"])

                result = await session.scalar(stmt)
                return result or 0
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting detections")
                raise

    async def count_by_species(
        self,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        include_localized_names: bool = False,
        language_code: str = "en",
    ) -> dict[str, int] | list[dict[str, Any]]:
        """Count detections by species with optional localized names."""
        if include_localized_names and self.query_service:
            # Returns list of dicts with species summary info
            return await self.query_service.get_species_summary(
                language_code=language_code,
                since=start_date,
            )

        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(Detection.scientific_name, func.count(Detection.id).label("count"))

                if start_date:
                    stmt = stmt.where(Detection.timestamp >= start_date)
                if end_date:
                    stmt = stmt.where(Detection.timestamp <= end_date)

                stmt = stmt.group_by(Detection.scientific_name)
                stmt = stmt.order_by(func.count(Detection.id).desc())

                result = await session.execute(stmt)
                results = list(result)
                # Row objects support dictionary access in SQLAlchemy 2.0
                if not results:
                    return {}
                return {str(row["scientific_name"]): int(row["count"]) for row in results}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting by species")
                raise

    async def count_by_date(self, species: str | None = None) -> dict[date, int]:
        """Count detections by date with optional species filter."""
        async with self.database_service.get_async_db() as session:
            try:
                stmt = select(
                    func.date(Detection.timestamp).label("date"),
                    func.count(Detection.id).label("count"),
                )

                if species:
                    stmt = stmt.where(Detection.scientific_name == species)

                stmt = stmt.group_by(func.date(Detection.timestamp))
                stmt = stmt.order_by(func.date(Detection.timestamp))

                result = await session.execute(stmt)
                results = list(result)
                # Row objects support dictionary access in SQLAlchemy 2.0
                if not results:
                    return {}
                return {row["date"]: int(row["count"]) for row in results}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting by date")
                raise

    # ==================== Translation Helpers ====================

    def get_species_display_name(
        self,
        detection: DetectionBase | DetectionWithLocalization,
        prefer_translation: bool = True,
        language_code: str = "en",
    ) -> str:
        """Get display name respecting user preferences and database priority."""
        # If it's already a DetectionWithLocalization, use species display service
        if isinstance(detection, DetectionWithLocalization):
            return self.species_display.format_species_display(detection, prefer_translation)

        # For plain Detection, return basic name
        if prefer_translation and detection.common_name:
            return str(detection.common_name)
        # Ensure we return a string
        scientific = detection.scientific_name
        common = detection.common_name
        return str(scientific) if scientific else str(common) if common else "Unknown"

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

    # ==================== Analytics Methods ====================
    # Methods needed by AnalyticsManager for dashboard and visualizations

    async def get_detection_count(
        self, start_time: datetime.datetime, end_time: datetime.datetime
    ) -> int:
        """Get count of detections in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of detections in the time range
        """
        async with self.database_service.get_async_db() as session:
            try:
                count = await session.scalar(
                    select(func.count())
                    .select_from(Detection)
                    .where(Detection.timestamp >= start_time)
                    .where(Detection.timestamp <= end_time)
                )
                return count or 0
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error getting detection count")
                raise

    async def get_unique_species_count(
        self, start_time: datetime.datetime, end_time: datetime.datetime
    ) -> int:
        """Get count of unique species detected in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of unique species detected
        """
        async with self.database_service.get_async_db() as session:
            try:
                count = await session.scalar(
                    select(func.count(func.distinct(Detection.scientific_name)))
                    .where(Detection.timestamp >= start_time)
                    .where(Detection.timestamp <= end_time)
                )
                return count or 0
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error getting unique species count")
                raise

    async def get_storage_metrics(self) -> dict[str, Any]:
        """Get storage metrics for audio files.

        Returns:
            Dictionary with total_bytes and total_duration
        """
        async with self.database_service.get_async_db() as session:
            try:
                # Get total file size and duration
                result = await session.execute(
                    select(
                        func.sum(AudioFile.size_bytes).label("total_bytes"),
                        func.sum(AudioFile.duration).label("total_duration"),
                    )
                )
                row = result.first()

                if row:
                    return {
                        "total_bytes": row.total_bytes or 0,
                        "total_duration": row.total_duration or 0,
                    }
                return {"total_bytes": 0, "total_duration": 0}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error getting storage metrics")
                raise

    async def get_species_counts(
        self, start_time: datetime.datetime, end_time: datetime.datetime
    ) -> list[dict[str, Any]]:
        """Get species with their detection counts in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of dicts with scientific_name, common_name, and count
        """
        async with self.database_service.get_async_db() as session:
            try:
                result = await session.execute(
                    select(
                        Detection.scientific_name,
                        Detection.common_name,
                        func.count(Detection.id).label("count"),
                    )
                    .where(Detection.timestamp >= start_time)
                    .where(Detection.timestamp <= end_time)
                    .group_by(Detection.scientific_name, Detection.common_name)
                    .order_by(desc("count"))
                )

                return [
                    {
                        "scientific_name": row.scientific_name,
                        "common_name": row.common_name,
                        "count": row.count,
                    }
                    for row in result
                ]
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error getting species counts")
                raise

    async def get_hourly_counts(self, target_date: date) -> list[dict[str, Any]]:
        """Get hourly detection counts for a specific date.

        Args:
            target_date: Date to get hourly counts for

        Returns:
            List of dicts with hour and count
        """
        async with self.database_service.get_async_db() as session:
            try:
                # Convert date to datetime range
                start_time = datetime.datetime.combine(target_date, datetime.time.min)
                end_time = datetime.datetime.combine(target_date, datetime.time.max)

                # SQLite-specific hour extraction
                result = await session.execute(
                    select(
                        func.strftime("%H", Detection.timestamp).label("hour"),
                        func.count(Detection.id).label("count"),
                    )
                    .where(Detection.timestamp >= start_time)
                    .where(Detection.timestamp <= end_time)
                    .group_by(func.strftime("%H", Detection.timestamp))
                    .order_by("hour")
                )

                return [{"hour": int(row.hour), "count": row.count} for row in result]
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error getting hourly counts")
                raise

    # ==================== Raw Query Escape Hatch ====================

    async def execute_raw_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a raw SQL query. Use only for complex queries."""
        async with self.database_service.get_async_db() as session:
            try:
                result = await session.execute(query, params or {})
                return [dict(row) for row in result]
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error executing raw query")
                raise
