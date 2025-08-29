"""Service for detection queries with translation support.

This service handles all queries that need to join Detection records with species
and translation data from multiple databases (IOC, Avibase, PatLevin). It uses SQLite's
ATTACH DATABASE functionality to efficiently join across databases while minimizing
write operations to protect SD card longevity.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.models import Detection, DetectionBase, DetectionWithLocalization
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService

logger = logging.getLogger(__name__)


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
    ):
        """Initialize detection query service.

        Args:
            bnp_database_service: Main database service for detections
            multilingual_service: Multilingual database service (IOC/Avibase/PatLevin)
        """
        self.bnp_database_service = bnp_database_service
        self.multilingual_service = multilingual_service

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

    def _apply_species_filter(self, stmt: Select, species: str | list[str] | None) -> Select:
        """Apply species filter to query statement."""
        if not species:
            return stmt

        if isinstance(species, list):
            # Note: pyright doesn't recognize .in_() on SQLModel columns (known issue)
            return stmt.where(Detection.scientific_name.in_(species))  # type: ignore[attr-defined]
        else:
            return stmt.where(Detection.scientific_name == species)

    def _apply_date_filters(
        self, stmt: Select, start_date: datetime | None, end_date: datetime | None
    ) -> Select:
        """Apply date range filters to query statement."""
        if start_date:
            stmt = stmt.where(Detection.timestamp >= start_date)
        if end_date:
            stmt = stmt.where(Detection.timestamp <= end_date)
        return stmt

    def _apply_confidence_filters(
        self, stmt: Select, min_confidence: float | None, max_confidence: float | None
    ) -> Select:
        """Apply confidence range filters to query statement."""
        if min_confidence is not None:
            stmt = stmt.where(Detection.confidence >= min_confidence)
        if max_confidence is not None:
            stmt = stmt.where(Detection.confidence <= max_confidence)
        return stmt

    def _apply_ordering(self, stmt: Select, order_by: str, order_desc: bool) -> Select:
        """Apply ordering to query statement."""
        # Safely get the column attribute
        if hasattr(Detection, order_by):
            order_column = getattr(Detection, order_by)
        else:
            order_column = Detection.timestamp  # Default to timestamp

        if order_desc:
            return stmt.order_by(desc(order_column))
        else:
            return stmt.order_by(order_column)

    async def query_detections(
        self,
        species: str | list[str] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
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

        This is the main query method that handles all detection queries.
        """
        if include_localization:
            # Use localization-aware query
            return await self.get_detections_with_localization(
                limit=limit or 100,
                offset=offset or 0,
                language_code=language_code,
                since=start_date,
                scientific_name_filter=species if isinstance(species, str) else None,
                # Note: min/max confidence and end_date filters not yet supported
            )

        # Standard query without localization
        async with self.bnp_database_service.get_async_db() as session:
            stmt = select(Detection)

            # Apply filters using helper methods
            stmt = self._apply_species_filter(stmt, species)
            stmt = self._apply_date_filters(stmt, start_date, end_date)
            stmt = self._apply_confidence_filters(stmt, min_confidence, max_confidence)
            stmt = self._apply_ordering(stmt, order_by, order_desc)

            # Apply pagination
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars())

    async def get_detections_with_localization(
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
        async with self.bnp_database_service.get_async_db() as session:
            await self.multilingual_service.attach_all_to_session(session)
            try:
                return await self._execute_join_query(
                    session=session,
                    limit=limit,
                    offset=offset,
                    language_code=language_code,
                    since=since,
                    scientific_name_filter=scientific_name_filter,
                    family_filter=family_filter,
                )
            finally:
                await self.multilingual_service.detach_all_from_session(session)

    async def get_detection_with_localization(
        self, detection_id: UUID, language_code: str = "en"
    ) -> DetectionWithLocalization | None:
        """Get single detection with translation data by ID.

        Args:
            detection_id: Detection UUID
            language_code: Language for translations

        Returns:
            DetectionWithLocalization object or None if not found
        """
        async with self.bnp_database_service.get_async_db() as session:
            await self.multilingual_service.attach_all_to_session(session)
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

                result = await session.execute(
                    query_sql, {"detection_id": str(detection_id), "language_code": language_code}
                )
                result = result.fetchone()

                if not result:
                    return None

                # Create Detection object
                # Handle both string and UUID inputs for ID
                detection_id_val = result.id if isinstance(result.id, UUID) else UUID(result.id)  # type: ignore[attr-defined]
                audio_file_id_val = None
                if result.audio_file_id:  # type: ignore[attr-defined]
                    audio_file_id_val = (
                        result.audio_file_id  # type: ignore[attr-defined]
                        if isinstance(result.audio_file_id, UUID)  # type: ignore[attr-defined]
                        else UUID(result.audio_file_id)  # type: ignore[attr-defined]
                    )

                detection = Detection(
                    id=detection_id_val,
                    species_tensor=result.species_tensor,  # type: ignore[attr-defined]
                    scientific_name=result.scientific_name,  # type: ignore[attr-defined]
                    common_name=result.common_name,  # type: ignore[attr-defined]
                    confidence=result.confidence,  # type: ignore[attr-defined]
                    timestamp=self._parse_timestamp(result.timestamp),  # type: ignore[attr-defined]
                    audio_file_id=audio_file_id_val,
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

                return detection_with_l10n

            finally:
                await self.multilingual_service.detach_all_from_session(session)

    async def get_species_summary(
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
        async with self.bnp_database_service.get_async_db() as session:
            await self.multilingual_service.attach_all_to_session(session)
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

                result = await session.execute(query_sql, params)
                results = result.fetchall()

                # Debug logging
                logger.info(
                    f"Species summary query returned {len(results)} species "
                    f"for period since {params.get('since')}"
                )

                # Additional debugging - check what's actually in the database
                if len(results) == 0 and params.get("since"):
                    # Query to check recent detections
                    check_query = text("""
                        SELECT
                            COUNT(*) as total_detections,
                            MIN(timestamp) as earliest,
                            MAX(timestamp) as latest,
                            COUNT(CASE WHEN timestamp >= :since THEN 1 END)
                                as detections_after_since
                        FROM detections
                    """)
                    check_result = await session.execute(check_query, {"since": params["since"]})
                    check_row = check_result.fetchone()
                    if check_row:
                        logger.info(
                            f"Database check - Total: {check_row.total_detections}, "
                            f"Earliest: {check_row.earliest}, Latest: {check_row.latest}, "
                            f"After {params['since']}: {check_row.detections_after_since}"
                        )

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

                return species_summary

            finally:
                await self.multilingual_service.detach_all_from_session(session)

    async def get_family_summary(
        self, language_code: str = "en", since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get detection count summary by taxonomic family.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp

        Returns:
            List of family summary dictionaries
        """
        async with self.bnp_database_service.get_async_db() as session:
            await self.multilingual_service.attach_all_to_session(session)
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

                result = await session.execute(query_sql, params)
                results = result.fetchall()

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

                return family_summary

            finally:
                await self.multilingual_service.detach_all_from_session(session)

    async def _execute_join_query(
        self,
        session: AsyncSession,
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

        result = await session.execute(query_sql, params)
        results = result.fetchall()

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
