"""Service for detection queries with translation support.

This service handles all queries that need to join Detection records with species
and translation data from multiple databases (IOC, Avibase, PatLevin). It uses SQLite's
ATTACH DATABASE functionality to efficiently join across databases while minimizing
write operations to protect SD card longevity.
"""

import datetime
import logging
from datetime import datetime as dt
from typing import Any
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import AudioFile, Detection, DetectionBase, DetectionWithTaxa
from birdnetpi.species.display import SpeciesDisplayService

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
        core_database: CoreDatabaseService,
        species_database: SpeciesDatabaseService,
        species_display_service: SpeciesDisplayService | None = None,
    ):
        """Initialize detection query service.

        Args:
            core_database: Main database service for detections
            species_database: Species database service (IOC/Avibase/PatLevin)
            species_display_service: Optional service for species display formatting
        """
        self.core_database = core_database
        self.species_database = species_database
        self.species_display = species_display_service

    def _parse_timestamp(self, timestamp_value: dt | str | int | float) -> dt:
        """Parse timestamp from various formats.

        Args:
            timestamp_value: Timestamp as string, datetime, or other format

        Returns:
            Parsed datetime object
        """
        if isinstance(timestamp_value, dt):
            return timestamp_value
        if isinstance(timestamp_value, str):
            return date_parser.parse(timestamp_value)
        return dt.fromisoformat(str(timestamp_value))

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
        self, stmt: Select, start_date: dt | None, end_date: dt | None
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
        start_date: dt | None = None,
        end_date: dt | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str = "timestamp",
        order_desc: bool = True,
        language_code: str = "en",
    ) -> list[DetectionWithTaxa]:
        """Query detections with flexible filtering and taxa enrichment.

        This is the main query method that handles all detection queries.
        Always returns DetectionWithTaxa for consistent taxonomy data access.
        """
        # Always use taxa-enriched query
        return await self.get_detections_with_taxa(
            limit=limit or 100,
            offset=offset or 0,
            language_code=language_code,
            since=start_date,
            scientific_name_filter=species if isinstance(species, str) else None,
            # Note: min/max confidence and end_date filters not yet supported in taxa query
        )

    async def get_detections_with_taxa(
        self,
        limit: int = 100,
        offset: int = 0,
        language_code: str = "en",
        since: dt | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithTaxa]:
        """Get detections with taxonomy data.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            language_code: Language for translations (default: en)
            since: Only return detections after this timestamp
            scientific_name_filter: Filter by specific scientific name
            family_filter: Filter by taxonomic family

        Returns:
            List of DetectionWithTaxa objects
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
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
                await self.species_database.detach_all_from_session(session)

    async def get_detection_with_taxa(
        self, detection_id: UUID, language_code: str = "en"
    ) -> DetectionWithTaxa | None:
        """Get single detection with taxonomy data by ID.

        Args:
            detection_id: Detection UUID
            language_code: Language for translations

        Returns:
            DetectionWithTaxa object or None if not found
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
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

                detection_with_l10n = DetectionWithTaxa(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,  # type: ignore[attr-defined]
                    translated_name=result.translated_name,  # type: ignore[attr-defined]
                    family=result.family,  # type: ignore[attr-defined]
                    genus=result.genus,  # type: ignore[attr-defined]
                    order_name=result.order_name,  # type: ignore[attr-defined]
                )

                return detection_with_l10n

            finally:
                await self.species_database.detach_all_from_session(session)

    async def get_species_summary(
        self,
        language_code: str = "en",
        since: dt | None = None,
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
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
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
                await self.species_database.detach_all_from_session(session)

    async def get_family_summary(
        self, language_code: str = "en", since: dt | None = None
    ) -> list[dict[str, Any]]:
        """Get detection count summary by taxonomic family.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp

        Returns:
            List of family summary dictionaries
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
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
                await self.species_database.detach_all_from_session(session)

    async def _execute_join_query(
        self,
        session: AsyncSession,
        limit: int,
        offset: int,
        language_code: str,
        since: dt | None = None,
        scientific_name_filter: str | None = None,
        family_filter: str | None = None,
    ) -> list[DetectionWithTaxa]:
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
                DetectionWithTaxa(
                    detection=detection,
                    ioc_english_name=result.ioc_english_name,  # type: ignore[attr-defined]
                    translated_name=result.translated_name,  # type: ignore[attr-defined]
                    family=result.family,  # type: ignore[attr-defined]
                    genus=result.genus,  # type: ignore[attr-defined]
                    order_name=result.order_name,  # type: ignore[attr-defined]
                )
            )

        return detection_data_list

    async def get_detection_count(self, start_time: dt, end_time: dt) -> int:
        """Get count of detections in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of detections in the time range
        """
        async with self.core_database.get_async_db() as session:
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

    async def get_unique_species_count(self, start_time: dt, end_time: dt) -> int:
        """Get count of unique species detected in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Number of unique species detected
        """
        async with self.core_database.get_async_db() as session:
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
        async with self.core_database.get_async_db() as session:
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

    async def get_species_counts(self, start_time: dt, end_time: dt) -> list[dict[str, Any]]:
        """Get species with their detection counts in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of dicts with scientific_name, common_name, and count
        """
        async with self.core_database.get_async_db() as session:
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

    async def get_hourly_counts(self, target_date: datetime.date) -> list[dict[str, Any]]:
        """Get hourly detection counts for a specific date.

        Args:
            target_date: Date to get hourly counts for

        Returns:
            List of dicts with hour and count
        """
        async with self.core_database.get_async_db() as session:
            try:
                # Convert date to datetime range
                start_time = dt.combine(target_date, datetime.time.min)
                end_time = dt.combine(target_date, datetime.time.max)

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

    async def count_detections(self, filters: dict[str, Any] | None = None) -> int:
        """Count detections with optional filters.

        Args:
            filters: Optional dict with keys:
                - species: Filter by scientific name
                - start_date: Start datetime
                - end_date: End datetime
                - min_confidence: Minimum confidence threshold

        Returns:
            Number of detections matching filters
        """
        async with self.core_database.get_async_db() as session:
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
        start_date: dt | None = None,
        end_date: dt | None = None,
    ) -> dict[str, int]:
        """Count detections by species.

        Args:
            start_date: Optional start datetime
            end_date: Optional end datetime

        Returns:
            Dict mapping scientific name to detection count
        """
        async with self.core_database.get_async_db() as session:
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
                if not results:
                    return {}
                return {str(row["scientific_name"]): int(row["count"]) for row in results}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting by species")
                raise

    async def count_by_date(self, species: str | None = None) -> dict[datetime.date, int]:
        """Count detections by date with optional species filter.

        Args:
            species: Optional scientific name to filter by

        Returns:
            Dict mapping dates to detection counts
        """
        async with self.core_database.get_async_db() as session:
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
                if not results:
                    return {}
                return {row["date"]: int(row["count"]) for row in results}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting by date")
                raise

    # ==================== Display Helpers ====================

    def get_species_display_name(
        self,
        detection: DetectionBase | DetectionWithTaxa,
        prefer_translation: bool = True,
        language_code: str = "en",
    ) -> str:
        """Get display name respecting user preferences and database priority.

        Args:
            detection: The detection to get display name for
            prefer_translation: Whether to prefer translated common name
            language_code: Language code for translation (unused but kept for compatibility)

        Returns:
            Formatted species display name
        """
        # If species display service is available and it's a DetectionWithTaxa, use it
        if self.species_display and isinstance(detection, DetectionWithTaxa):
            return self.species_display.format_species_display(detection, prefer_translation)

        # For plain Detection, return basic name
        if prefer_translation and detection.common_name:
            return str(detection.common_name)
        # Ensure we return a string
        scientific = detection.scientific_name
        common = detection.common_name
        return str(scientific) if scientific else str(common) if common else "Unknown"
