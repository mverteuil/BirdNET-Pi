"""Service for detection queries requiring IOC database joins.

This service handles all queries that need to join Detection records with IOC species
and translation data. It uses SQLite's ATTACH DATABASE functionality to efficiently
join across databases while minimizing write operations to protect SD card longevity.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from birdnetpi.models.database_models import Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.ioc_database_service import IOCDatabaseService


class DetectionWithIOCData:
    """Data class for detection with IOC information."""

    def __init__(
        self,
        detection: Detection,
        ioc_english_name: str | None = None,
        translated_name: str | None = None,
        family: str | None = None,
        genus: str | None = None,
        order_name: str | None = None,
    ):
        self.detection = detection
        self.ioc_english_name = ioc_english_name
        self.translated_name = translated_name
        self.family = family
        self.genus = genus
        self.order_name = order_name

    @property
    def id(self) -> UUID:
        """Get detection ID."""
        return self.detection.id

    @property
    def scientific_name(self) -> str:
        """Get scientific name."""
        return self.detection.scientific_name

    @property
    def common_name(self) -> str:
        """Get common name from tensor."""
        return self.detection.common_name

    @property
    def confidence(self) -> float:
        """Get detection confidence."""
        return self.detection.confidence

    @property
    def timestamp(self) -> datetime:
        """Get detection timestamp."""
        return self.detection.timestamp

    def get_best_common_name(self, prefer_translation: bool = False) -> str:
        """Get the best available common name for display.
        
        Args:
            prefer_translation: Whether to prefer translated name over IOC English name
            
        Returns:
            Best available common name
        """
        if prefer_translation and self.translated_name:
            return self.translated_name
        if self.ioc_english_name:
            return self.ioc_english_name
        if self.translated_name:
            return self.translated_name
        return self.common_name or self.scientific_name


class DetectionQueryService:
    """Service for Detection queries requiring IOC database joins."""

    def __init__(self, db_service: DatabaseService, ioc_db_service: IOCDatabaseService):
        """Initialize detection query service.

        Args:
            db_service: Main database service for detections
            ioc_db_service: IOC reference database service
        """
        self.db_service = db_service
        self.ioc_db_service = ioc_db_service

    def get_detections_with_ioc_data(
        self,
        limit: int = 100,
        offset: int = 0,
        language_code: str = "en",
        since: datetime | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithIOCData]:
        """Get detections with IOC species and translation data.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            language_code: Language for translations (default: en)
            since: Only return detections after this timestamp
            scientific_name_filter: Filter by specific scientific name
            family_filter: Filter by taxonomic family

        Returns:
            List of DetectionWithIOCData objects
        """
        with self.db_service.get_db() as session:
            self.ioc_db_service.attach_to_session(session)
            try:
                return self._execute_join_query(
                    session=session,
                    limit=limit,
                    offset=offset,
                    language_code=language_code,
                    since=since,
                    scientific_name_filter=scientific_name_filter,
                    family_filter=family_filter,
                )
            finally:
                self.ioc_db_service.detach_from_session(session)

    def get_detection_with_ioc_data(
        self, detection_id: UUID, language_code: str = "en"
    ) -> DetectionWithIOCData | None:
        """Get single detection with IOC data by ID.

        Args:
            detection_id: Detection UUID
            language_code: Language for translations

        Returns:
            DetectionWithIOCData object or None if not found
        """
        with self.db_service.get_db() as session:
            self.ioc_db_service.attach_to_session(session)
            try:
                query_sql = text("""
                    SELECT 
                        d.id,
                        d.species_tensor,
                        d.scientific_name,
                        d.common_name,
                        d.confidence,
                        d.timestamp,
                        d.audio_file_id,
                        d.latitude,
                        d.longitude,
                        d.species_confidence_threshold,
                        d.week,
                        d.sensitivity_setting,
                        d.overlap,
                        s.english_name as ioc_english_name,
                        COALESCE(t.common_name, s.english_name) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name 
                        AND t.language_code = :language_code
                    WHERE d.id = :detection_id
                """)

                result = session.execute(
                    query_sql, {"detection_id": str(detection_id), "language_code": language_code}
                ).fetchone()

                if not result:
                    return None

                # Create Detection object
                detection = Detection(
                    id=UUID(result.id),
                    species_tensor=result.species_tensor,
                    scientific_name=result.scientific_name,
                    common_name=result.common_name,
                    confidence=result.confidence,
                    timestamp=result.timestamp,
                    audio_file_id=UUID(result.audio_file_id) if result.audio_file_id else None,
                    latitude=result.latitude,
                    longitude=result.longitude,
                    species_confidence_threshold=result.species_confidence_threshold,
                    week=result.week,
                    sensitivity_setting=result.sensitivity_setting,
                    overlap=result.overlap,
                )

                return DetectionWithIOCData(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,
                    translated_name=result.translated_name,
                    family=result.family,
                    genus=result.genus,
                    order_name=result.order_name,
                )

            finally:
                self.ioc_db_service.detach_from_session(session)

    def get_species_summary(
        self,
        language_code: str = "en",
        since: datetime | None = None,
        family_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get detection count summary by species with IOC data.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family

        Returns:
            List of species summary dictionaries
        """
        with self.db_service.get_db() as session:
            self.ioc_db_service.attach_to_session(session)
            try:
                where_clause = "WHERE 1=1"
                params: dict[str, Any] = {"language_code": language_code}

                if since:
                    where_clause += " AND d.timestamp >= :since"
                    params["since"] = since

                if family_filter:
                    where_clause += " AND s.family = :family"
                    params["family"] = family_filter

                query_sql = text(f"""
                    SELECT 
                        d.scientific_name,
                        COUNT(*) as detection_count,
                        AVG(d.confidence) as avg_confidence,
                        MAX(d.timestamp) as latest_detection,
                        s.english_name as ioc_english_name,
                        COALESCE(t.common_name, s.english_name) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name 
                        AND t.language_code = :language_code
                    {where_clause}
                    GROUP BY d.scientific_name, s.english_name, t.common_name, s.family, s.genus, s.order_name
                    ORDER BY detection_count DESC
                """)

                results = session.execute(query_sql, params).fetchall()

                return [
                    {
                        "scientific_name": result.scientific_name,
                        "detection_count": result.detection_count,
                        "avg_confidence": round(result.avg_confidence, 3),
                        "latest_detection": result.latest_detection,
                        "ioc_english_name": result.ioc_english_name,
                        "translated_name": result.translated_name,
                        "family": result.family,
                        "genus": result.genus,
                        "order_name": result.order_name,
                        "best_common_name": result.translated_name or result.ioc_english_name,
                    }
                    for result in results
                ]

            finally:
                self.ioc_db_service.detach_from_session(session)

    def get_family_summary(
        self, language_code: str = "en", since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get detection count summary by taxonomic family.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp

        Returns:
            List of family summary dictionaries
        """
        with self.db_service.get_db() as session:
            self.ioc_db_service.attach_to_session(session)
            try:
                where_clause = "WHERE s.family IS NOT NULL"
                params: dict[str, Any] = {"language_code": language_code}

                if since:
                    where_clause += " AND d.timestamp >= :since"
                    params["since"] = since

                query_sql = text(f"""
                    SELECT 
                        s.family,
                        s.order_name,
                        COUNT(*) as detection_count,
                        COUNT(DISTINCT d.scientific_name) as species_count,
                        AVG(d.confidence) as avg_confidence,
                        MAX(d.timestamp) as latest_detection
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    {where_clause}
                    GROUP BY s.family, s.order_name
                    ORDER BY detection_count DESC
                """)

                results = session.execute(query_sql, params).fetchall()

                return [
                    {
                        "family": result.family,
                        "order_name": result.order_name,
                        "detection_count": result.detection_count,
                        "species_count": result.species_count,
                        "avg_confidence": round(result.avg_confidence, 3),
                        "latest_detection": result.latest_detection,
                    }
                    for result in results
                ]

            finally:
                self.ioc_db_service.detach_from_session(session)

    def _execute_join_query(
        self,
        session: Session,
        limit: int,
        offset: int,
        language_code: str,
        since: datetime | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithIOCData]:
        """Execute the main JOIN query with filters."""
        where_clause = "WHERE 1=1"
        params: dict[str, Any] = {"language_code": language_code, "limit": limit, "offset": offset}

        if since:
            where_clause += " AND d.timestamp >= :since"
            params["since"] = since

        if scientific_name_filter:
            where_clause += " AND d.scientific_name = :scientific_name"
            params["scientific_name"] = scientific_name_filter

        if family_filter:
            where_clause += " AND s.family = :family"
            params["family"] = family_filter

        query_sql = text(f"""
            SELECT 
                d.id,
                d.species_tensor,
                d.scientific_name,
                d.common_name,
                d.confidence,
                d.timestamp,
                d.audio_file_id,
                d.latitude,
                d.longitude,
                d.species_confidence_threshold,
                d.week,
                d.sensitivity_setting,
                d.overlap,
                s.english_name as ioc_english_name,
                COALESCE(t.common_name, s.english_name) as translated_name,
                s.family,
                s.genus,
                s.order_name
            FROM detections d
            LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
            LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name 
                AND t.language_code = :language_code
            {where_clause}
            ORDER BY d.timestamp DESC
            LIMIT :limit OFFSET :offset
        """)

        results = session.execute(query_sql, params).fetchall()

        detection_data_list = []
        for result in results:
            # Create Detection object
            detection = Detection(
                id=UUID(result.id),
                species_tensor=result.species_tensor,
                scientific_name=result.scientific_name,
                common_name=result.common_name,
                confidence=result.confidence,
                timestamp=result.timestamp,
                audio_file_id=UUID(result.audio_file_id) if result.audio_file_id else None,
                latitude=result.latitude,
                longitude=result.longitude,
                species_confidence_threshold=result.species_confidence_threshold,
                week=result.week,
                sensitivity_setting=result.sensitivity_setting,
                overlap=result.overlap,
            )

            detection_data_list.append(
                DetectionWithIOCData(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,
                    translated_name=result.translated_name,
                    family=result.family,
                    genus=result.genus,
                    order_name=result.order_name,
                )
            )

        return detection_data_list