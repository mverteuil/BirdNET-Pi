"""Service for detection queries with translation support.

This service handles all queries that need to join Detection records with species
and translation data from multiple databases (IOC, Avibase, PatLevin). It uses SQLite's
ATTACH DATABASE functionality to efficiently join across databases while minimizing
write operations to protect SD card longevity.
"""

import hashlib
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import text
from sqlalchemy.orm import Session

from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.models.database_models import Detection
from birdnetpi.services.database_service import DatabaseService


class DetectionWithLocalization:
    """Data class for detection with localization information."""

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
        return self.detection.id  # type: ignore[return-value]

    @property
    def scientific_name(self) -> str:
        """Get scientific name."""
        return self.detection.scientific_name  # type: ignore[return-value]

    @property
    def common_name(self) -> str:
        """Get common name from detection."""
        return self.detection.common_name  # type: ignore[return-value]

    @property
    def confidence(self) -> float:
        """Get detection confidence."""
        return self.detection.confidence  # type: ignore[return-value]

    @property
    def timestamp(self) -> datetime:
        """Get detection timestamp."""
        return self.detection.timestamp  # type: ignore[return-value]


class DetectionQueryService:
    """Service for Detection queries with translation support.

    This service provides enriched detection data by joining BirdNET-Pi detection records
    with IOC (International Ornithological Committee) taxonomic data and multilingual
    translations from Avibase and PatLevin databases. It supports dynamic language switching
    and provides comprehensive species information including family, genus, order, and
    localized common names.
    """

    def __init__(
        self,
        bnp_database_service: DatabaseService,
        multilingual_service: MultilingualDatabaseService,
        cache_ttl: int = 300,
    ):
        """Initialize detection query service.

        Args:
            bnp_database_service: Main database service for detections
            multilingual_service: Multilingual database service (IOC/Avibase/PatLevin)
            cache_ttl: Cache time-to-live in seconds (default: 5 minutes)
        """
        self.bnp_database_service = bnp_database_service
        self.multilingual_service = multilingual_service
        self.cache_ttl = cache_ttl

        # In-memory cache: {cache_key: (data, expiry_timestamp)}
        self._cache = {}

    def _generate_cache_key(
        self, method: str, **kwargs: str | int | float | datetime | None
    ) -> str:
        """Generate a cache key based on method name and parameters.

        Args:
            method: Method name being cached
            **kwargs: Method parameters

        Returns:
            SHA-256 hash of the cache key components
        """
        # Sort parameters for consistent key generation
        key_parts = [method]
        for key, value in sorted(kwargs.items()):
            if isinstance(value, datetime):
                key_parts.append(f"{key}:{value.isoformat()}")
            elif value is not None:
                key_parts.append(f"{key}:{value!s}")

        cache_string = "|".join(key_parts)
        return hashlib.sha256(cache_string.encode()).hexdigest()

    def _get_from_cache(
        self, cache_key: str
    ) -> DetectionWithLocalization | list[DetectionWithLocalization] | list[dict[str, Any]] | None:
        """Get data from cache if available and not expired.

        Args:
            cache_key: Cache key to retrieve

        Returns:
            Cached data if available and valid, None otherwise
        """
        if cache_key not in self._cache:
            return None

        data, expiry = self._cache[cache_key]
        current_time = time.time()

        if current_time > expiry:
            # Cache expired, remove it
            del self._cache[cache_key]
            return None

        return data

    def _set_cache(
        self,
        cache_key: str,
        data: (DetectionWithLocalization | list[DetectionWithLocalization] | list[dict[str, Any]]),
    ) -> None:
        """Store data in cache with TTL expiry.

        Args:
            cache_key: Cache key to store under
            data: Data to cache
        """
        expiry = time.time() + self.cache_ttl
        self._cache[cache_key] = (data, expiry)

        # Simple cache cleanup: remove expired entries periodically
        if len(self._cache) > 100:  # Cleanup when cache gets large
            self._cleanup_expired_cache()

    def _cleanup_expired_cache(self) -> None:
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [key for key, (_, expiry) in self._cache.items() if current_time > expiry]
        for key in expired_keys:
            del self._cache[key]

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def _parse_timestamp(self, timestamp_value: datetime | str | int | float) -> datetime:
        """Parse timestamp from various formats.

        Args:
            timestamp_value: Timestamp as string, datetime, or other format

        Returns:
            Parsed datetime object
        """
        if isinstance(timestamp_value, datetime):
            return timestamp_value
        if isinstance(timestamp_value, str):
            return date_parser.parse(timestamp_value)
        return datetime.fromisoformat(str(timestamp_value))

    def get_detections_with_localization(
        self,
        limit: int = 100,
        offset: int = 0,
        language_code: str = "en",
        since: datetime | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithLocalization]:
        """Get detections with translation data.

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
        with self.bnp_database_service.get_db() as session:
            self.multilingual_service.attach_all_to_session(session)
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
                self.multilingual_service.detach_all_from_session(session)

    def get_detection_with_localization(
        self, detection_id: UUID, language_code: str = "en"
    ) -> DetectionWithLocalization | None:
        """Get single detection with translation data by ID.

        Args:
            detection_id: Detection UUID
            language_code: Language for translations

        Returns:
            DetectionWithLocalization object or None if not found
        """
        # Generate cache key for single detection
        cache_key = self._generate_cache_key(
            "get_detection_with_localization",
            detection_id=str(detection_id),
            language_code=language_code,
        )

        # Try to get from cache first
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None and isinstance(cached_result, DetectionWithLocalization):
            return cached_result

        with self.bnp_database_service.get_db() as session:
            self.multilingual_service.attach_all_to_session(session)
            try:
                # Updated query to use COALESCE across all three databases
                # Priority: IOC → PatLevin → Avibase
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
                        COALESCE(s.english_name, d.common_name) as ioc_english_name,
                        COALESCE(
                            t.common_name,
                            p.common_name,
                            a.common_name,
                            s.english_name,
                            d.common_name
                        ) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name
                        AND t.language_code = :language_code
                    LEFT JOIN patlevin.patlevin_labels p
                        ON LOWER(p.scientific_name) = LOWER(d.scientific_name)
                        AND p.language_code = :language_code
                    LEFT JOIN avibase.avibase_names a
                        ON LOWER(a.scientific_name) = LOWER(d.scientific_name)
                        AND a.language_code = :language_code
                    WHERE d.id = :detection_id
                """)

                result = session.execute(
                    query_sql, {"detection_id": str(detection_id), "language_code": language_code}
                ).fetchone()

                if not result:
                    return None

                # Create Detection object
                detection = Detection(
                    id=UUID(result.id),  # type: ignore[attr-defined]
                    species_tensor=result.species_tensor,  # type: ignore[attr-defined]
                    scientific_name=result.scientific_name,  # type: ignore[attr-defined]
                    common_name=result.common_name,  # type: ignore[attr-defined]
                    confidence=result.confidence,  # type: ignore[attr-defined]
                    timestamp=self._parse_timestamp(result.timestamp),  # type: ignore[attr-defined]
                    audio_file_id=UUID(result.audio_file_id) if result.audio_file_id else None,  # type: ignore[attr-defined]
                    latitude=result.latitude,  # type: ignore[attr-defined]
                    longitude=result.longitude,  # type: ignore[attr-defined]
                    species_confidence_threshold=result.species_confidence_threshold,  # type: ignore[attr-defined]
                    week=result.week,  # type: ignore[attr-defined]
                    sensitivity_setting=result.sensitivity_setting,  # type: ignore[attr-defined]
                    overlap=result.overlap,  # type: ignore[attr-defined]
                )

                detection_with_l10n = DetectionWithLocalization(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,  # type: ignore[attr-defined]
                    translated_name=result.translated_name,  # type: ignore[attr-defined]
                    family=result.family,  # type: ignore[attr-defined]
                    genus=result.genus,  # type: ignore[attr-defined]
                    order_name=result.order_name,  # type: ignore[attr-defined]
                )

                # Cache the result before returning
                self._set_cache(cache_key, detection_with_l10n)
                return detection_with_l10n

            finally:
                self.multilingual_service.detach_all_from_session(session)

    def get_species_summary(
        self,
        language_code: str = "en",
        since: datetime | None = None,
        family_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get detection count summary by species with translation data.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family

        Returns:
            List of species summary dictionaries
        """
        # Generate cache key for species summary
        cache_key = self._generate_cache_key(
            "get_species_summary",
            language_code=language_code,
            since=since,
            family_filter=family_filter,
        )

        # Try to get from cache first
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None and isinstance(cached_result, list):
            return cached_result  # type: ignore[return-value]

        with self.bnp_database_service.get_db() as session:
            self.multilingual_service.attach_all_to_session(session)
            try:
                where_clause = "WHERE 1=1"
                params: dict[str, Any] = {"language_code": language_code}

                if since:
                    where_clause += " AND d.timestamp >= :since"
                    params["since"] = since

                if family_filter:
                    where_clause += " AND s.family = :family"
                    params["family"] = family_filter

                # Updated query with COALESCE across all three databases
                query_sql = text(f"""
                    SELECT
                        d.scientific_name,
                        COUNT(*) as detection_count,
                        AVG(d.confidence) as avg_confidence,
                        MAX(d.timestamp) as latest_detection,
                        s.english_name as ioc_english_name,
                        COALESCE(
                            t.common_name,
                            p.common_name,
                            a.common_name,
                            s.english_name,
                            d.common_name
                        ) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name
                        AND t.language_code = :language_code
                    LEFT JOIN patlevin.patlevin_labels p
                        ON LOWER(p.scientific_name) = LOWER(d.scientific_name)
                        AND p.language_code = :language_code
                    LEFT JOIN avibase.avibase_names a
                        ON LOWER(a.scientific_name) = LOWER(d.scientific_name)
                        AND a.language_code = :language_code
                    {where_clause}
                    GROUP BY d.scientific_name, s.english_name, translated_name, s.family, s.genus,
                             s.order_name
                    ORDER BY detection_count DESC
                """)

                results = session.execute(query_sql, params).fetchall()

                species_summary = [
                    {
                        "scientific_name": result.scientific_name,  # type: ignore[attr-defined]
                        "detection_count": result.detection_count,  # type: ignore[attr-defined]
                        "avg_confidence": round(float(result.avg_confidence), 3),  # type: ignore[attr-defined]
                        "latest_detection": self._parse_timestamp(result.latest_detection)  # type: ignore[attr-defined]
                        if result.latest_detection  # type: ignore[attr-defined]
                        else None,
                        "ioc_english_name": result.ioc_english_name,  # type: ignore[attr-defined]
                        "translated_name": result.translated_name,  # type: ignore[attr-defined]
                        "family": result.family,  # type: ignore[attr-defined]
                        "genus": result.genus,  # type: ignore[attr-defined]
                        "order_name": result.order_name,  # type: ignore[attr-defined]
                        "best_common_name": result.translated_name or result.ioc_english_name,  # type: ignore[attr-defined]
                    }
                    for result in results
                ]

                # Cache the result before returning
                self._set_cache(cache_key, species_summary)
                return species_summary

            finally:
                self.multilingual_service.detach_all_from_session(session)

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
        # Generate cache key for family summary
        cache_key = self._generate_cache_key(
            "get_family_summary", language_code=language_code, since=since
        )

        # Try to get from cache first
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None and isinstance(cached_result, list):
            return cached_result  # type: ignore[return-value]

        with self.bnp_database_service.get_db() as session:
            self.multilingual_service.attach_all_to_session(session)
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

                family_summary = [
                    {
                        "family": result.family,  # type: ignore[attr-defined]
                        "order_name": result.order_name,  # type: ignore[attr-defined]
                        "detection_count": result.detection_count,  # type: ignore[attr-defined]
                        "species_count": result.species_count,  # type: ignore[attr-defined]
                        "avg_confidence": round(float(result.avg_confidence), 3),  # type: ignore[attr-defined]
                        "latest_detection": self._parse_timestamp(result.latest_detection)  # type: ignore[attr-defined]
                        if result.latest_detection  # type: ignore[attr-defined]
                        else None,
                    }
                    for result in results
                ]

                # Cache the result before returning
                self._set_cache(cache_key, family_summary)
                return family_summary

            finally:
                self.multilingual_service.detach_all_from_session(session)

    def _execute_join_query(
        self,
        session: Session,
        limit: int,
        offset: int,
        language_code: str,
        since: datetime | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithLocalization]:
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

        # Updated query with COALESCE across all three databases
        # Priority: IOC → PatLevin → Avibase
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
                COALESCE(s.english_name, d.common_name) as ioc_english_name,
                COALESCE(
                    t.common_name,
                    p.common_name,
                    a.common_name,
                    s.english_name,
                    d.common_name
                ) as translated_name,
                s.family,
                s.genus,
                s.order_name
            FROM detections d
            LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
            LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name
                AND t.language_code = :language_code
            LEFT JOIN patlevin.patlevin_labels p
                ON LOWER(p.scientific_name) = LOWER(d.scientific_name)
                AND p.language_code = :language_code
            LEFT JOIN avibase.avibase_names a
                ON LOWER(a.scientific_name) = LOWER(d.scientific_name)
                AND a.language_code = :language_code
            {where_clause}
            ORDER BY d.timestamp DESC
            LIMIT :limit OFFSET :offset
        """)

        results = session.execute(query_sql, params).fetchall()

        detection_data_list = []
        for result in results:
            # Create Detection object
            detection = Detection(
                id=UUID(result.id),  # type: ignore[attr-defined]
                species_tensor=result.species_tensor,  # type: ignore[attr-defined]
                scientific_name=result.scientific_name,  # type: ignore[attr-defined]
                common_name=result.common_name,  # type: ignore[attr-defined]
                confidence=result.confidence,  # type: ignore[attr-defined]
                timestamp=self._parse_timestamp(result.timestamp),  # type: ignore[attr-defined]
                audio_file_id=UUID(result.audio_file_id) if result.audio_file_id else None,  # type: ignore[attr-defined]
                latitude=result.latitude,  # type: ignore[attr-defined]
                longitude=result.longitude,  # type: ignore[attr-defined]
                species_confidence_threshold=result.species_confidence_threshold,  # type: ignore[attr-defined]
                week=result.week,  # type: ignore[attr-defined]
                sensitivity_setting=result.sensitivity_setting,  # type: ignore[attr-defined]
                overlap=result.overlap,  # type: ignore[attr-defined]
            )

            detection_data_list.append(
                DetectionWithLocalization(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,  # type: ignore[attr-defined]
                    translated_name=result.translated_name,  # type: ignore[attr-defined]
                    family=result.family,  # type: ignore[attr-defined]
                    genus=result.genus,  # type: ignore[attr-defined]
                    order_name=result.order_name,  # type: ignore[attr-defined]
                )
            )

        return detection_data_list
