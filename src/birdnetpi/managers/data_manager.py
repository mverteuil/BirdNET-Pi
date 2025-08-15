"""Single source of truth for all detection data access.

This manager provides a unified interface for accessing detection data,
coordinating between the database service, multilingual service, and
species display service. It acts as a facade to simplify data access
patterns while preserving the underlying service architecture.
"""

import datetime
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_query_service import (
    DetectionQueryService,
    DetectionWithLocalization,
)
from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.services.species_display_service import SpeciesDisplayService
from birdnetpi.web.models.detection import DetectionEvent


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
        detection_query_service: DetectionQueryService | None = None,
    ) -> None:
        """Initialize the DataManager with required services.

        Args:
            database_service: Core database service for BirdNET-Pi data
            multilingual_service: Handles IOC, Avibase, PatLevin databases
            species_display_service: Complex display logic for species names
            detection_query_service: Legacy service for compatibility (will be absorbed)
        """
        self.database_service = database_service
        self.multilingual = multilingual_service
        self.species_display = species_display_service
        self.query_service = detection_query_service

    # ==================== Core CRUD Operations ====================

    def get_detection_by_id(self, detection_id: int) -> Detection | None:
        """Get a single detection by its ID."""
        with self.database_service.get_db() as session:
            try:
                return session.query(Detection).filter(Detection.id == detection_id).first()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error retrieving detection by ID: {e}")
                raise

    def get_all_detections(
        self, limit: int | None = None, offset: int | None = None
    ) -> list[Detection]:
        """Get all detections with optional pagination."""
        with self.database_service.get_db() as session:
            try:
                query = session.query(Detection)
                if offset:
                    query = query.offset(offset)
                if limit:
                    query = query.limit(limit)
                return query.all()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error retrieving all detections: {e}")
                raise

    def create_detection(self, detection_event: DetectionEvent) -> Detection:
        """Create a new detection record from a DetectionEvent.

        Note: This is data access only. Event emission should be handled
        by DetectionManager or a separate event service.
        """
        with self.database_service.get_db() as session:
            try:
                # Create AudioFile if audio data provided
                audio_file = None
                if detection_event.audio_file_path:
                    audio_file = AudioFile(
                        file_path=detection_event.audio_file_path,
                        duration=detection_event.duration,
                        size_bytes=detection_event.size_bytes,
                    )
                    session.add(audio_file)
                    session.flush()

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
                session.commit()
                session.refresh(detection)
                return detection
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error creating detection: {e}")
                raise

    def update_detection(self, detection_id: int, updates: dict[str, Any]) -> Detection | None:
        """Update a detection record."""
        with self.database_service.get_db() as session:
            try:
                detection = session.query(Detection).filter(Detection.id == detection_id).first()
                if detection:
                    for key, value in updates.items():
                        if hasattr(detection, key):
                            setattr(detection, key, value)
                    session.commit()
                    session.refresh(detection)
                return detection
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error updating detection: {e}")
                raise

    def delete_detection(self, detection_id: int) -> bool:
        """Delete a detection record."""
        with self.database_service.get_db() as session:
            try:
                detection = session.query(Detection).filter(Detection.id == detection_id).first()
                if detection:
                    session.delete(detection)
                    session.commit()
                    return True
                return False
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error deleting detection: {e}")
                raise

    # ==================== Query Methods ====================

    def query_detections(  # noqa: C901
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
    ) -> list[Detection] | list[DetectionWithLocalization]:
        """Query detections with flexible filtering and optional localization.

        This is the main query method that consolidates various filtering patterns.
        """
        if include_localization and self.query_service:
            # Use DetectionQueryService for localization
            return self.query_service.get_detections_with_localization(
                limit=limit or 100,
                offset=offset or 0,
                language_code=language_code,
                since=start_date,
                scientific_name_filter=species if isinstance(species, str) else None,
            )

        # Standard query without localization
        with self.database_service.get_db() as session:
            try:
                query = session.query(Detection)

                # Apply filters
                if species:
                    if isinstance(species, list):
                        query = query.filter(Detection.scientific_name.in_(species))
                    else:
                        query = query.filter(Detection.scientific_name == species)

                if start_date:
                    query = query.filter(Detection.timestamp >= start_date)
                if end_date:
                    query = query.filter(Detection.timestamp <= end_date)
                if min_confidence is not None:
                    query = query.filter(Detection.confidence >= min_confidence)
                if max_confidence is not None:
                    query = query.filter(Detection.confidence <= max_confidence)

                # Apply ordering
                order_column = getattr(Detection, order_by, Detection.timestamp)
                if order_desc:
                    query = query.order_by(order_column.desc())
                else:
                    query = query.order_by(order_column)

                # Apply pagination
                if offset:
                    query = query.offset(offset)
                if limit:
                    query = query.limit(limit)

                return query.all()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error querying detections: {e}")
                raise

    def get_detections_with_localization(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        language_code: str = "en",
    ) -> list[DetectionWithLocalization]:
        """Get detections with localized names from multiple databases.

        Priority: IOC → PatLevin → Avibase
        """
        if not self.query_service:
            raise RuntimeError("DetectionQueryService not available for localization")

        # Convert filters to method parameters
        kwargs = {
            "limit": limit or 100,
            "offset": offset or 0,
            "language_code": language_code,
        }

        if filters:
            kwargs.update(
                {
                    "since": filters.get("start_date"),
                    "scientific_name_filter": filters.get("species"),
                    "family_filter": filters.get("family"),
                }
            )

        return self.query_service.get_detections_with_localization(**kwargs)

    def get_detection_with_localization(
        self,
        detection_id: int,
        language_code: str = "en",
    ) -> DetectionWithLocalization | None:
        """Get single detection with localized names."""
        detections = self.get_detections_with_localization(
            filters={"detection_id": detection_id},
            limit=1,
            language_code=language_code,
        )
        return detections[0] if detections else None

    # ==================== Count Methods ====================

    def count_detections(self, filters: dict[str, Any] | None = None) -> int:
        """Count detections with optional filters."""
        with self.database_service.get_db() as session:
            try:
                query = session.query(func.count(Detection.id))

                if filters:
                    if "species" in filters:
                        query = query.filter(Detection.scientific_name == filters["species"])
                    if "start_date" in filters:
                        query = query.filter(Detection.timestamp >= filters["start_date"])
                    if "end_date" in filters:
                        query = query.filter(Detection.timestamp <= filters["end_date"])
                    if "min_confidence" in filters:
                        query = query.filter(Detection.confidence >= filters["min_confidence"])

                return query.scalar() or 0
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error counting detections: {e}")
                raise

    def count_by_species(
        self,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        include_localized_names: bool = False,
        language_code: str = "en",
    ) -> dict[str, int] | list[dict[str, Any]]:
        """Count detections by species with optional localized names."""
        if include_localized_names and self.query_service:
            # Returns list of dicts with species summary info
            return self.query_service.get_species_summary(
                language_code=language_code,
                since=start_date,
            )

        with self.database_service.get_db() as session:
            try:
                query = session.query(
                    Detection.scientific_name, func.count(Detection.id).label("count")
                )

                if start_date:
                    query = query.filter(Detection.timestamp >= start_date)
                if end_date:
                    query = query.filter(Detection.timestamp <= end_date)

                query = query.group_by(Detection.scientific_name)
                query = query.order_by(func.count(Detection.id).desc())

                results = query.all()
                return {row[0]: row[1] for row in results}
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error counting by species: {e}")
                raise

    def count_by_date(self, species: str | None = None) -> dict[date, int]:
        """Count detections by date with optional species filter."""
        with self.database_service.get_db() as session:
            try:
                query = session.query(
                    func.date(Detection.timestamp).label("date"),
                    func.count(Detection.id).label("count"),
                )

                if species:
                    query = query.filter(Detection.scientific_name == species)

                query = query.group_by(func.date(Detection.timestamp))
                query = query.order_by(func.date(Detection.timestamp))

                results = query.all()
                return {row[0]: row[1] for row in results}
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error counting by date: {e}")
                raise

    # ==================== Translation Helpers ====================

    def get_species_display_name(
        self,
        detection: Detection | DetectionWithLocalization,
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

    # ==================== Specialized Queries (Migrated from DetectionManager) ====================

    def get_recent_detections(self, limit: int = 10) -> list[Detection]:
        """Get the most recent detections."""
        result = self.query_detections(limit=limit, order_by="timestamp", order_desc=True)
        # Ensure we return list[Detection] type
        if isinstance(result, list) and (not result or isinstance(result[0], Detection)):
            return result  # type: ignore
        return []

    def get_detections_by_species(self, species_name: str) -> list[Detection]:
        """Get all detections for a specific species."""
        result = self.query_detections(species=species_name)
        # Ensure we return list[Detection] type
        if isinstance(result, list) and (not result or isinstance(result[0], Detection)):
            return result  # type: ignore
        return []

    def get_detection_counts_by_date_range(
        self, start_date: datetime.datetime, end_date: datetime.datetime
    ) -> dict[str, int]:
        """Get total detection count and unique species count within a date range."""
        with self.database_service.get_db() as session:
            try:
                total_count = (
                    session.query(Detection)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .count()
                )
                unique_species_count = (
                    session.query(Detection.scientific_name)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .distinct()
                    .count()
                )
                return {
                    "total_count": total_count,
                    "unique_species": unique_species_count,
                }
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error getting detection counts by date range: {e}")
                raise

    def get_top_species_with_prior_counts(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        prior_start_date: datetime.datetime,
        prior_end_date: datetime.datetime,
    ) -> list[dict[str, Any]]:
        """Get top 10 species for current and prior periods."""
        with self.database_service.get_db() as session:
            try:
                current_week_subquery = (
                    session.query(
                        Detection.scientific_name.label("scientific_name"),
                        func.coalesce(
                            Detection.common_name,
                            Detection.scientific_name,
                        ).label("common_name"),
                        func.count(Detection.scientific_name).label("current_count"),
                    )
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .group_by(Detection.scientific_name)
                    .subquery()
                )

                prior_week_subquery = (
                    session.query(
                        Detection.scientific_name.label("scientific_name"),
                        func.count(Detection.scientific_name).label("prior_count"),
                    )
                    .filter(Detection.timestamp.between(prior_start_date, prior_end_date))
                    .group_by(Detection.scientific_name)
                    .subquery()
                )

                results = (
                    session.query(
                        current_week_subquery.c.scientific_name,
                        current_week_subquery.c.common_name,
                        current_week_subquery.c.current_count,
                        func.coalesce(prior_week_subquery.c.prior_count, 0).label("prior_count"),
                    )
                    .outerjoin(
                        prior_week_subquery,
                        current_week_subquery.c.scientific_name
                        == prior_week_subquery.c.scientific_name,
                    )
                    .order_by(current_week_subquery.c.current_count.desc())
                    .limit(10)
                    .all()
                )

                return [
                    {
                        "scientific_name": row[0],
                        "common_name": row[1],
                        "current_count": row[2],
                        "prior_count": row[3],
                    }
                    for row in results
                ]
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error getting top species with prior counts: {e}")
                raise

    def get_new_species_data(
        self, start_date: datetime.datetime, end_date: datetime.datetime
    ) -> list[dict[str, Any]]:
        """Get new species not present before the start date."""
        with self.database_service.get_db() as session:
            try:
                # Subquery to find all species detected before the start_date
                prior_species_subquery = (
                    session.query(Detection.scientific_name)
                    .filter(Detection.timestamp < start_date)
                    .distinct()
                )

                # Query for new species in current range
                new_species_results = (
                    session.query(
                        Detection.scientific_name,
                        func.coalesce(
                            Detection.common_name,
                            Detection.scientific_name,
                        ).label("common_name"),
                        func.count(Detection.scientific_name).label("count"),
                    )
                    .filter(
                        Detection.timestamp.between(start_date, end_date),
                        ~Detection.scientific_name.in_(prior_species_subquery),
                    )
                    .group_by(Detection.scientific_name)
                    .order_by(func.count(Detection.scientific_name).desc())
                    .all()
                )

                return [
                    {"species": row[0], "common_name": row[1], "count": row[2]}
                    for row in new_species_results
                ]
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error getting new species data: {e}")
                raise

    def get_best_detections(self, limit: int = 10) -> list[Detection]:
        """Get the best detection for each species, sorted by confidence."""
        with self.database_service.get_db() as session:
            try:
                # Subquery to rank detections by confidence for each species
                ranked_subquery = session.query(
                    Detection.id,
                    func.row_number()
                    .over(
                        partition_by=Detection.scientific_name,
                        order_by=Detection.confidence.desc(),
                    )
                    .label("rn"),
                ).subquery()

                # Get the IDs of the top-ranked detection for each species
                best_detection_ids_query = session.query(ranked_subquery.c.id).filter(
                    ranked_subquery.c.rn == 1
                )

                # Get the full detection objects for those IDs
                best_detections = (
                    session.query(Detection)
                    .filter(Detection.id.in_(best_detection_ids_query))
                    .order_by(Detection.confidence.desc())
                    .limit(limit)
                    .all()
                )

                return best_detections
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error getting best detections: {e}")
                raise

    # ==================== AudioFile Operations ====================

    def get_audio_file_by_path(self, file_path: str) -> AudioFile | None:
        """Get an audio file record by its path."""
        with self.database_service.get_db() as session:
            try:
                return session.query(AudioFile).filter(AudioFile.file_path == file_path).first()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error retrieving audio file: {e}")
                raise

    # ==================== Raw Query Escape Hatch ====================

    def execute_raw_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a raw SQL query. Use only for complex queries."""
        with self.database_service.get_db() as session:
            try:
                result = session.execute(query, params or {})
                return [dict(row) for row in result]
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error executing raw query: {e}")
                raise
