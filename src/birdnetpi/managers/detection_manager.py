import datetime
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_query_service import (
    DetectionQueryService,
    DetectionWithLocalization,
)
from birdnetpi.services.species_display_service import SpeciesDisplayService
from birdnetpi.utils.signals import detection_signal
from birdnetpi.web.models.detection import DetectionEvent


class DetectionManager:
    """Manages detection operations via DatabaseService."""

    def __init__(
        self,
        bnp_database_service: DatabaseService,
        detection_query_service: DetectionQueryService | None = None,
        species_display_service: SpeciesDisplayService | None = None,
    ) -> None:
        self.bnp_database_service = bnp_database_service
        self.detection_query_service = detection_query_service
        self.species_display_service = species_display_service

    def _get_formatted_species_name(
        self, detection: DetectionWithLocalization, prefer_translation: bool = False
    ) -> str:
        """Get formatted species name using SpeciesDisplayService if available, else fallback."""
        if self.species_display_service:
            return self.species_display_service.format_species_display(
                detection, prefer_translation
            )
        # Fallback implementation if SpeciesDisplayService not available
        if prefer_translation:
            if detection.translated_name:
                return detection.translated_name
            if detection.ioc_english_name:
                return detection.ioc_english_name
        else:
            if detection.ioc_english_name:
                return detection.ioc_english_name
            if detection.translated_name:
                return detection.translated_name
        return detection.common_name or detection.scientific_name

    def create_detection(self, detection_event: DetectionEvent) -> Detection:
        """Create a new detection record and associated audio file record in the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                # Create AudioFile record
                audio_file = AudioFile(
                    file_path=detection_event.audio_file_path,
                    duration=detection_event.duration,
                    size_bytes=detection_event.size_bytes,
                )
                db.add(audio_file)
                db.flush()  # Flush to get audio_file.id before committing

                # Create Detection record
                detection = Detection(
                    species_tensor=detection_event.species_tensor,
                    scientific_name=detection_event.scientific_name,
                    common_name=detection_event.common_name,
                    confidence=detection_event.confidence,
                    timestamp=detection_event.timestamp,
                    audio_file_id=audio_file.id,
                    latitude=detection_event.latitude,
                    longitude=detection_event.longitude,
                    species_confidence_threshold=detection_event.species_confidence_threshold,
                    week=detection_event.week,
                    sensitivity_setting=detection_event.sensitivity_setting,
                    overlap=detection_event.overlap,
                )
                db.add(detection)
                db.commit()
                db.refresh(detection)

                # Emit Blinker signal
                detection_signal.send(self, detection=detection)

                return detection
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error creating detection: {e}")
                raise

    def get_all_detections(self) -> list[Detection]:
        """Retrieve all detection records from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).all()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detections: {e}")
                raise

    def get_audio_file_by_path(self, file_path: Path) -> AudioFile | None:
        """Retrieve an AudioFile record by its file path."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(AudioFile).filter_by(file_path=file_path).first()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving audio file: {e}")
                raise

    def delete_detection(self, detection_id: int) -> None:
        """Delete a detection record from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                detection = db.query(Detection).get(detection_id)
                if detection:
                    db.delete(detection)
                    db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error deleting detection: {e}")
                raise

    def get_detections_by_species(self, species_name: str) -> list[Detection]:
        """Retrieve all detection records for a given species from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).filter_by(scientific_name=species_name).all()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detections by species: {e}")
                raise

    def get_detection_counts_by_date_range(
        self, start_date: datetime.datetime, end_date: datetime.datetime
    ) -> dict:
        """Get total detection count and unique species count within a date range."""
        with self.bnp_database_service.get_db() as db:
            try:
                total_count = (
                    db.query(Detection)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .count()
                )
                unique_species_count = (
                    db.query(Detection.scientific_name)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .distinct()
                    .count()
                )
                return {
                    "total_count": total_count,
                    "unique_species": unique_species_count,
                }
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting detection counts by date range: {e}")
                raise

    def get_top_species_with_prior_counts(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        prior_start_date: datetime.datetime,
        prior_end_date: datetime.datetime,
    ) -> list[dict]:
        """Fetch top 10 species for current and prior weeks."""
        with self.bnp_database_service.get_db() as db:
            try:
                current_week_subquery = (
                    db.query(
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
                    db.query(
                        Detection.scientific_name.label("scientific_name"),
                        func.count(Detection.scientific_name).label("prior_count"),
                    )
                    .filter(Detection.timestamp.between(prior_start_date, prior_end_date))
                    .group_by(Detection.scientific_name)
                    .subquery()
                )

                results = (
                    db.query(
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
                        "scientific_name": row[0],  # scientific_name
                        "common_name": row[1],  # common_name
                        "current_count": row[2],  # current_count
                        "prior_count": row[3],  # prior_count
                    }
                    for row in results
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting top species with prior counts: {e}")
                raise

    def get_new_species_data(
        self, start_date: datetime.datetime, end_date: datetime.datetime
    ) -> list[dict]:
        """Fetch new species not present in prior data."""
        with self.bnp_database_service.get_db() as db:
            try:
                # Subquery to find all species detected before the start_date
                prior_species_subquery = (
                    db.query(Detection.scientific_name)
                    .filter(Detection.timestamp < start_date)
                    .distinct()
                )

                # Query for new species in current range, excluding prior_species_subquery
                new_species_results = (
                    db.query(
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
                    {"species": row[0], "count": row[2]}
                    for row in new_species_results  # scientific_name, common_name, count
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting new species data: {e}")
                raise

    def get_most_recent_detections(self, limit: int = 10) -> list[dict]:
        """Retrieve the most recent detection records from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                recent_detections = (
                    db.query(Detection).order_by(Detection.timestamp.desc()).limit(limit).all()
                )
                return [
                    {
                        "date": d.timestamp.strftime("%Y-%m-%d"),
                        "time": d.timestamp.strftime("%H:%M:%S"),
                        "scientific_name": d.scientific_name or "",
                        "common_name": d.common_name or "",
                        "confidence": d.confidence,
                        "latitude": d.latitude,
                        "longitude": d.longitude,
                        "species_confidence_threshold": d.species_confidence_threshold,
                        "week": d.week,
                        "sensitivity_setting": d.sensitivity_setting,
                        "overlap": d.overlap,
                    }
                    for d in recent_detections
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting most recent detections: {e}")
                raise

    def get_best_detections(self, limit: int = 10) -> list[dict]:
        """Retrieve the best detection for each species, sorted by confidence."""
        with self.bnp_database_service.get_db() as db:
            try:
                # Subquery to rank detections by confidence for each species
                ranked_subquery = db.query(
                    Detection.id,
                    func.row_number()
                    .over(
                        partition_by=Detection.scientific_name,
                        order_by=Detection.confidence.desc(),
                    )
                    .label("rn"),
                ).subquery()

                # Get the IDs of the top-ranked detection for each species
                best_detection_ids_query = db.query(ranked_subquery.c.id).filter(
                    ranked_subquery.c.rn == 1
                )

                # Get the full detection objects for those IDs
                best_detections = (
                    db.query(Detection)
                    .filter(Detection.id.in_(best_detection_ids_query))
                    .order_by(Detection.confidence.desc())
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "date": d.timestamp.strftime("%Y-%m-%d"),
                        "time": d.timestamp.strftime("%H:%M:%S"),
                        "scientific_name": d.scientific_name or "",
                        "common_name": d.common_name or "",
                        "confidence": d.confidence,
                        "latitude": d.latitude,
                        "longitude": d.longitude,
                        "species_confidence_threshold": d.species_confidence_threshold,
                        "week": d.week,
                        "sensitivity_setting": d.sensitivity_setting,
                        "overlap": d.overlap,
                    }
                    for d in best_detections
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting best detections: {e}")
                raise

    def get_detection(self, detection_id: int) -> Detection | None:
        """Retrieve a single detection record from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).get(detection_id)
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detection: {e}")
                raise

    def get_total_detections(self) -> int:
        """Retrieve the total count of all detection records from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).count()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving total detections: {e}")
                raise

    def get_recent_detections(self, limit: int = 10) -> list[Detection]:
        """Retrieve recent detection records from the database."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).order_by(Detection.timestamp.desc()).limit(limit).all()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving recent detections: {e}")
                raise

    def get_detection_by_id(self, detection_id: int) -> Detection | None:
        """Retrieve a detection by its ID."""
        with self.bnp_database_service.get_db() as db:
            try:
                return db.query(Detection).filter(Detection.id == detection_id).first()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detection by ID: {e}")
                raise

    def get_detections_count_by_date(self, target_date: date) -> int:
        """Get count of detections for a specific date."""
        with self.bnp_database_service.get_db() as db:
            try:
                start_datetime = datetime.datetime.combine(target_date, datetime.time.min)
                end_datetime = datetime.datetime.combine(target_date, datetime.time.max)

                return (
                    db.query(Detection)
                    .filter(Detection.timestamp >= start_datetime)
                    .filter(Detection.timestamp <= end_datetime)
                    .count()
                )
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detection count by date: {e}")
                raise

    def update_detection_location(
        self, detection_id: int, latitude: float, longitude: float
    ) -> bool:
        """Update the location for a specific detection."""
        with self.bnp_database_service.get_db() as db:
            try:
                detection = db.query(Detection).filter(Detection.id == detection_id).first()
                if detection:
                    detection.latitude = latitude  # type: ignore[misc]
                    detection.longitude = longitude  # type: ignore[misc]
                    db.commit()
                    return True
                return False
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error updating detection location: {e}")
                raise

    def get_detections_with_localization(
        self,
        limit: int = 100,
        offset: int = 0,
        language_code: str = "en",
        since: datetime.datetime | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithLocalization]:
        """Get detections with translation data.

        This method uses the DetectionQueryService to join detection data with
        multilingual taxonomic information from IOC, PatLevin, and Avibase databases,
        providing enriched data including translated names, family, genus, and order information.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            language_code: Language for translations (default: en)
            since: Only return detections after this timestamp
            scientific_name_filter: Filter by specific scientific name
            family_filter: Filter by taxonomic family

        Returns:
            List of DetectionWithLocalization objects
        """
        if not self.detection_query_service:
            raise RuntimeError(
                "DetectionQueryService not available - using fallback to regular detections"
            )

        return self.detection_query_service.get_detections_with_localization(
            limit=limit,
            offset=offset,
            language_code=language_code,
            since=since,
            scientific_name_filter=scientific_name_filter,
            family_filter=family_filter,
        )

    def get_most_recent_detections_with_localization(
        self, limit: int = 10, language_code: str = "en"
    ) -> list[dict]:
        """Retrieve the most recent detection records with localization data from the database."""
        if not self.detection_query_service:
            # Fallback to existing method
            return self.get_most_recent_detections(limit)

        try:
            detections_with_l10n = self.detection_query_service.get_detections_with_localization(
                limit=limit, language_code=language_code
            )
            return [
                {
                    "date": d.timestamp.strftime("%Y-%m-%d"),
                    "time": d.timestamp.strftime("%H:%M:%S"),
                    "scientific_name": d.scientific_name or "",
                    "common_name": self._get_formatted_species_name(d, prefer_translation=True),
                    "confidence": d.confidence,
                    "latitude": d.detection.latitude,
                    "longitude": d.detection.longitude,
                    "species_confidence_threshold": d.detection.species_confidence_threshold,
                    "week": d.detection.week,
                    "sensitivity_setting": d.detection.sensitivity_setting,
                    "overlap": d.detection.overlap,
                    "ioc_english_name": d.ioc_english_name,
                    "translated_name": d.translated_name,
                    "family": d.family,
                    "genus": d.genus,
                    "order_name": d.order_name,
                }
                for d in detections_with_l10n
            ]
        except Exception as e:
            print(f"Error getting most recent detections with localization: {e}")
            # Fallback to existing method
            return self.get_most_recent_detections(limit)

    def get_species_summary(
        self,
        language_code: str = "en",
        since: datetime.datetime | None = None,
        family_filter: str | None = None,
    ) -> list[dict]:
        """Get detection count summary by species with localization data.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family

        Returns:
            List of species summary dictionaries
        """
        if not self.detection_query_service:
            raise RuntimeError("DetectionQueryService not available")

        return self.detection_query_service.get_species_summary(
            language_code=language_code, since=since, family_filter=family_filter
        )

    def get_family_summary(
        self, language_code: str = "en", since: datetime.datetime | None = None
    ) -> list[dict]:
        """Get detection count summary by taxonomic family.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp

        Returns:
            List of family summary dictionaries
        """
        if not self.detection_query_service:
            raise RuntimeError("DetectionQueryService not available")

        return self.detection_query_service.get_family_summary(
            language_code=language_code, since=since
        )
