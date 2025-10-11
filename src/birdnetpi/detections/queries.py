"""Service for detection queries with translation support.

This service handles all queries that need to join Detection records with species
and translation data from multiple databases (IOC, Wikidata). It uses SQLite's
ATTACH DATABASE functionality to efficiently join across databases while minimizing
write operations to protect SD card longevity.
"""

import datetime
import logging
from collections import defaultdict
from datetime import datetime as dt
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import TextClause

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import AudioFile, Detection, DetectionWithTaxa
from birdnetpi.location.models import Weather

logger = logging.getLogger(__name__)


class BestRecordingRow(Protocol):
    """Protocol for best recording query result rows."""

    id: str
    timestamp: Any  # Can be datetime, str, int, or float
    confidence: float
    scientific_name: str
    common_name: str
    audio_file_id: str | None
    family: str | None
    order_name: str | None
    translated_name: str | None


class DetectionQueryService:
    """Service for Detection queries with translation support.

    This service provides enriched detection data by joining BirdNET-Pi detection records
    with IOC (International Ornithological Committee) taxonomic data and multilingual
    translations from Wikidata. It supports dynamic language switching and provides
    comprehensive species information including family, genus, order, and localized
    common names.
    """

    def __init__(
        self,
        core_database: CoreDatabaseService,
        species_database: SpeciesDatabaseService,
        config: BirdNETConfig,
    ):
        """Initialize detection query service.

        Args:
            core_database: Main database service for detections
            species_database: Species database service (IOC/Wikidata)
            config: BirdNET configuration with language settings
        """
        self.core_database = core_database
        self.species_database = species_database
        self.config = config

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
        *,  # All parameters are keyword-only for clarity
        species: str | list[str] | None = None,
        family: str | None = None,
        genus: str | None = None,
        start_date: dt | None = None,
        end_date: dt | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str = "timestamp",
        order_desc: bool = True,
        include_first_detections: bool = False,
    ) -> list[DetectionWithTaxa]:
        """Query detections with flexible filtering and taxa enrichment.

        This is the main query method that handles all detection queries.
        Always returns DetectionWithTaxa for consistent taxonomy data access.

        Args:
            species: Filter by scientific name(s) - string or list
            family: Filter by taxonomic family
            genus: Filter by taxonomic genus
            start_date: Only return detections after this timestamp
            end_date: Only return detections before this timestamp
            min_confidence: Minimum confidence threshold
            max_confidence: Maximum confidence threshold
            limit: Maximum number of results (None = no limit)
            offset: Number of results to skip
            order_by: Field to order by (default: timestamp)
            order_desc: Whether to order descending (default: True)
            include_first_detections: Include first detection flags (adds overhead)

        Returns:
            List of DetectionWithTaxa objects
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                return await self._execute_join_query(
                    session=session,
                    limit=limit,
                    offset=offset or 0,
                    start_date=start_date,
                    end_date=end_date,
                    scientific_name_filter=species,
                    family_filter=family,
                    genus_filter=genus,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                    order_by=order_by,
                    order_desc=order_desc,
                    include_first_detections=include_first_detections,
                )
            finally:
                await self.species_database.detach_all_from_session(session)

    async def get_detections_with_taxa(
        self,
        limit: int = 100,
        offset: int = 0,
        *,  # Everything after this is keyword-only
        start_date: dt | None = None,
        end_date: dt | None = None,
        scientific_name_filter: str | list[str] | None = None,
        family_filter: str | None = None,
        genus_filter: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        order_by: str = "timestamp",
        order_desc: bool = True,
        # Legacy parameter name support
        since: dt | None = None,
    ) -> list[DetectionWithTaxa]:
        """Get detections with taxonomy data.

        DEPRECATED: Use query_detections() instead. This method exists for backward compatibility.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            start_date: Only return detections after this timestamp
            end_date: Only return detections before this timestamp
            scientific_name_filter: Filter by scientific name(s) - string or list
            family_filter: Filter by taxonomic family
            genus_filter: Filter by taxonomic genus
            min_confidence: Minimum confidence threshold
            max_confidence: Maximum confidence threshold
            order_by: Field to order by (default: timestamp)
            order_desc: Whether to order descending (default: True)
            since: Deprecated - use start_date instead

        Returns:
            List of DetectionWithTaxa objects
        """
        # Support legacy parameter name
        if since and not start_date:
            start_date = since

        # Delegate to the main query method
        return await self.query_detections(
            species=scientific_name_filter,
            family=family_filter,
            genus=genus_filter,
            start_date=start_date,
            end_date=end_date,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
        )

    async def get_detection_with_taxa(self, detection_id: UUID) -> DetectionWithTaxa | None:
        """Get single detection with taxonomy data by ID.

        Args:
            detection_id: Detection UUID

        Returns:
            DetectionWithTaxa object or None if not found
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                # Updated query for 2-database architecture (IOC + Wikidata)
                # Priority: IOC → Wikidata
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
                            w.common_name,
                            s.english_name,
                            d.common_name
                        ) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                        AND t.language_code = :language_code
                    LEFT JOIN wikidata.translations w
                        ON w.avibase_id = (
                            SELECT i.avibase_id
                            FROM ioc.species i
                            WHERE i.scientific_name = d.scientific_name
                        )
                        AND w.language_code = :language_code
                    WHERE d.id = :detection_id
                """)

                result = await session.execute(
                    query_sql,
                    {
                        "detection_id": detection_id.hex,  # SQLite stores UUIDs without hyphens
                        "language_code": self.config.language,
                    },
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

    def _format_species_summary_result(
        self,
        result: Any,  # noqa: ANN401
        include_first_detections: bool,
    ) -> dict[str, Any]:
        """Format a single species summary result.

        Args:
            result: Database result row
            include_first_detections: Whether to include first detection fields

        Returns:
            Formatted species data dictionary
        """
        species_data = {
            "scientific_name": result.scientific_name,  # type: ignore[attr-defined]
            "detection_count": result.detection_count,  # type: ignore[attr-defined]
            "avg_confidence": round(float(result.avg_confidence), 3),  # type: ignore[attr-defined]
            "latest_detection": self._parse_timestamp(result.latest_detection).isoformat()  # type: ignore[attr-defined]
            if result.latest_detection  # type: ignore[attr-defined]
            else None,
            "ioc_english_name": result.ioc_english_name,  # type: ignore[attr-defined]
            "translated_name": result.translated_name,  # type: ignore[attr-defined]
            "family": result.family,  # type: ignore[attr-defined]
            "genus": result.genus,  # type: ignore[attr-defined]
            "order_name": result.order_name,  # type: ignore[attr-defined]
            "best_common_name": result.translated_name or result.ioc_english_name,  # type: ignore[attr-defined]
        }

        # Add first detection fields if they exist
        # (as ISO strings for JSON serialization)
        if include_first_detections:
            if hasattr(result, "first_ever_detection") and result.first_ever_detection:
                species_data["first_ever_detection"] = self._parse_timestamp(
                    result.first_ever_detection
                ).isoformat()  # type: ignore[attr-defined]
            if hasattr(result, "first_period_detection") and result.first_period_detection:
                species_data["first_period_detection"] = self._parse_timestamp(
                    result.first_period_detection
                ).isoformat()  # type: ignore[attr-defined]

        return species_data

    def _build_species_summary_where_clause(
        self,
        since: dt | None,
        family_filter: str | None,
        params: dict[str, Any],
    ) -> str:
        """Build WHERE clause for species summary query."""
        where_clause = "WHERE 1=1"

        if since:
            where_clause += " AND d.timestamp >= :since"
            params["since"] = since

        if family_filter:
            where_clause += " AND s.family = :family"
            params["family"] = family_filter

        return where_clause

    def _build_species_summary_query(
        self,
        where_clause: str,
        include_first_detections: bool,
        since: dt | None = None,
    ) -> str:
        """Build SQL query for species summary."""
        if include_first_detections:
            return self._build_query_with_first_detections(where_clause, since)
        return self._build_simple_species_query(where_clause)

    def _build_query_with_first_detections(
        self,
        where_clause: str,
        since: dt | None,
    ) -> str:
        """Build species summary query with first detection tracking."""
        # Build first_period_detection column based on whether since is provided
        if since:
            first_period_col = (
                "MIN(CASE WHEN d.timestamp >= :since "
                "THEN d.timestamp END) as first_period_detection,"
            )
        else:
            first_period_col = "NULL as first_period_detection,"

        return f"""
            SELECT
                d.scientific_name,
                COUNT(*) as detection_count,
                AVG(d.confidence) as avg_confidence,
                MAX(d.timestamp) as latest_detection,
                MIN(d.timestamp) as first_ever_detection,
                {first_period_col}
                MAX(s.english_name) as ioc_english_name,
                MAX(COALESCE(
                    t.common_name,
                    w.common_name,
                    s.english_name,
                    d.common_name
                )) as translated_name,
                MAX(s.family) as family,
                MAX(s.genus) as genus,
                MAX(s.order_name) as order_name
            FROM detections d
            LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
            LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                AND t.language_code = :language_code
            LEFT JOIN wikidata.translations w
                ON w.avibase_id = (
                    SELECT i.avibase_id
                    FROM ioc.species i
                    WHERE i.scientific_name = d.scientific_name
                )
                AND w.language_code = :language_code
            {where_clause}
            GROUP BY d.scientific_name
            ORDER BY detection_count DESC
        """

    def _build_simple_species_query(self, where_clause: str) -> str:
        """Build simple species summary query without first detections."""
        return f"""
            SELECT
                d.scientific_name,
                COUNT(*) as detection_count,
                AVG(d.confidence) as avg_confidence,
                MAX(d.timestamp) as latest_detection,
                s.english_name as ioc_english_name,
                COALESCE(
                    t.common_name,
                    w.common_name,
                    s.english_name,
                    d.common_name
                ) as translated_name,
                s.family,
                s.genus,
                s.order_name
            FROM detections d
            LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
            LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                AND t.language_code = :language_code
            LEFT JOIN wikidata.translations w
                ON w.avibase_id = (
                    SELECT i.avibase_id
                    FROM ioc.species i
                    WHERE i.scientific_name = d.scientific_name
                )
                AND w.language_code = :language_code
            {where_clause}
            GROUP BY d.scientific_name, s.english_name, translated_name,
                     s.family, s.genus, s.order_name
            ORDER BY detection_count DESC
        """

    async def get_species_summary(
        self,
        since: dt | None = None,
        family_filter: str | None = None,
        include_first_detections: bool = False,
    ) -> list[dict[str, Any]]:
        """Get detection count summary by species with translation data.

        Args:
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family
            include_first_detections: Include first detection timestamps (adds overhead)

        Returns:
            List of species summary dictionaries
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                params: dict[str, Any] = {"language_code": self.config.language}

                # Build WHERE clause
                where_clause = self._build_species_summary_where_clause(
                    since, family_filter, params
                )

                # Build query SQL
                query_string = self._build_species_summary_query(
                    where_clause, include_first_detections, since
                )

                # Safe: WHERE clause uses pre-defined fragments, user data is parameterized
                query_sql = text(query_string)  # nosemgrep

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

                species_summary = []
                for result in results:
                    species_data = {
                        "scientific_name": result.scientific_name,  # type: ignore[attr-defined]
                        "detection_count": result.detection_count,  # type: ignore[attr-defined]
                        "avg_confidence": round(float(result.avg_confidence), 3),  # type: ignore[attr-defined]
                        "latest_detection": self._parse_timestamp(
                            result.latest_detection
                        ).isoformat()  # type: ignore[attr-defined]
                        if result.latest_detection  # type: ignore[attr-defined]
                        else None,
                        "ioc_english_name": result.ioc_english_name,  # type: ignore[attr-defined]
                        "translated_name": result.translated_name,  # type: ignore[attr-defined]
                        "family": result.family,  # type: ignore[attr-defined]
                        "genus": result.genus,  # type: ignore[attr-defined]
                        "order_name": result.order_name,  # type: ignore[attr-defined]
                        "best_common_name": result.translated_name or result.ioc_english_name,  # type: ignore[attr-defined]
                    }

                    # Add first detection fields if they exist
                    # (as ISO strings for JSON serialization)
                    if include_first_detections:
                        if hasattr(result, "first_ever_detection") and result.first_ever_detection:
                            species_data["first_ever_detection"] = self._parse_timestamp(
                                result.first_ever_detection
                            ).isoformat()  # type: ignore[attr-defined]
                        if (
                            hasattr(result, "first_period_detection")
                            and result.first_period_detection
                        ):
                            species_data["first_period_detection"] = self._parse_timestamp(
                                result.first_period_detection
                            ).isoformat()  # type: ignore[attr-defined]

                    species_summary.append(species_data)

                return species_summary

            finally:
                await self.species_database.detach_all_from_session(session)

    async def get_family_summary(self, since: dt | None = None) -> list[dict[str, Any]]:
        """Get detection count summary by taxonomic family.

        Args:
            since: Only include detections after this timestamp

        Returns:
            List of family summary dictionaries
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                where_clause = "WHERE s.family IS NOT NULL"
                params: dict[str, Any] = {"language_code": self.config.language}

                if since:
                    where_clause += " AND d.timestamp >= :since"
                    params["since"] = since

                # Safe: WHERE clause uses pre-defined fragments, user data is parameterized
                query_sql = text(  # nosemgrep
                    f"""
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
                """
                )

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

    def _add_scientific_name_filter(
        self,
        where_clause: str,
        params: dict[str, Any],
        scientific_name_filter: str | list[str] | None,
    ) -> str:
        """Add scientific name filter to WHERE clause."""
        if not scientific_name_filter:
            return where_clause

        if isinstance(scientific_name_filter, list):
            # Create parameterized IN clause
            species_params = [f":species_{i}" for i in range(len(scientific_name_filter))]
            where_clause += f" AND d.scientific_name IN ({','.join(species_params)})"
            for i, species in enumerate(scientific_name_filter):
                params[f"species_{i}"] = species
        else:
            where_clause += " AND d.scientific_name = :scientific_name"
            params["scientific_name"] = scientific_name_filter

        return where_clause

    def _build_where_clause_and_params(
        self,
        limit: int | None,
        offset: int,
        *,  # Everything after this is keyword-only
        start_date: dt | None = None,
        end_date: dt | None = None,
        scientific_name_filter: str | list[str] | None = None,
        family_filter: str | None = None,
        genus_filter: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Build WHERE clause and parameters for the query."""
        where_clause = "WHERE 1=1"
        params: dict[str, Any] = {"language_code": self.config.language, "offset": offset}

        # Only add limit to params if it's not None
        if limit is not None:
            params["limit"] = limit

        # Date filters
        if start_date:
            where_clause += " AND d.timestamp >= :start_date"
            params["start_date"] = start_date

        if end_date:
            where_clause += " AND d.timestamp <= :end_date"
            params["end_date"] = end_date

        # Scientific name filter - delegate to helper method
        where_clause = self._add_scientific_name_filter(
            where_clause, params, scientific_name_filter
        )

        # Taxonomy filters
        if family_filter:
            where_clause += " AND s.family = :family"
            params["family"] = family_filter

        if genus_filter:
            where_clause += " AND s.genus = :genus"
            params["genus"] = genus_filter

        # Confidence filters
        if min_confidence is not None:
            where_clause += " AND d.confidence >= :min_confidence"
            params["min_confidence"] = min_confidence

        if max_confidence is not None:
            where_clause += " AND d.confidence <= :max_confidence"
            params["max_confidence"] = max_confidence

        return where_clause, params

    def _build_order_clause(self, order_by: str = "timestamp", order_desc: bool = True) -> str:
        """Build ORDER BY clause for the query."""
        # Map common field names to actual columns
        order_map = {
            "timestamp": "d.timestamp",
            "confidence": "d.confidence",
            "scientific_name": "d.scientific_name",
            "common_name": "d.common_name",
            "family": "s.family",
        }
        order_column = order_map.get(order_by, "d.timestamp")
        return f"ORDER BY {order_column} {'DESC' if order_desc else 'ASC'}"

    async def _execute_join_query(  # noqa: C901
        self,
        session: AsyncSession,
        limit: int | None,
        offset: int,
        *,  # Everything after this is keyword-only
        start_date: dt | None = None,
        end_date: dt | None = None,
        scientific_name_filter: str | list[str] | None = None,
        family_filter: str | None = None,
        genus_filter: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        order_by: str = "timestamp",
        order_desc: bool = True,
        include_first_detections: bool = False,
    ) -> list[DetectionWithTaxa]:
        """Execute the main JOIN query with filters.

        Complexity is inherent to SQL query construction with multiple variations:
        - With/without first detection window functions
        - With/without species database availability
        - Different filter combinations
        """
        # Build WHERE clause and parameters
        where_clause, params = self._build_where_clause_and_params(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            scientific_name_filter=scientific_name_filter,
            family_filter=family_filter,
            genus_filter=genus_filter,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
        )

        # Build ORDER BY clause
        order_clause = self._build_order_clause(order_by, order_desc)

        # Check if IOC database is attached by testing if the species table exists
        # This allows tests to work with mock species databases
        try:
            await session.execute(text("SELECT 1 FROM ioc.species LIMIT 1"))
            has_species_db = True
        except Exception:
            has_species_db = False

        # Build limit clause based on whether limit is None
        limit_clause = "" if limit is None else "LIMIT :limit"
        offset_clause = "OFFSET :offset" if offset > 0 else ""
        pagination_clause = f"{limit_clause} {offset_clause}".strip()

        if has_species_db:
            # Build query with or without window functions based on flag
            if include_first_detections:
                # Enhanced query with window functions for first detection info
                # IMPORTANT: We rank ALL detections globally first, then filter,
                # to ensure is_first_ever is accurate across all time periods

                # Build time-only WHERE clause for period_first CTE
                # This should only include date filters, not confidence/family/etc
                time_where_parts = []
                if start_date:
                    time_where_parts.append("timestamp >= :start_date")
                if end_date:
                    time_where_parts.append("timestamp <= :end_date")
                time_where_clause = (
                    "WHERE " + " AND ".join(time_where_parts) if time_where_parts else "WHERE 1=1"
                )

                # Safe: WHERE/ORDER clauses use pre-defined fragments, user data is parameterized
                query_sql = text(  # nosemgrep
                    f"""
                    WITH all_detections_ranked AS (
                        SELECT
                            id,
                            scientific_name,
                            timestamp,
                            ROW_NUMBER() OVER (
                                PARTITION BY scientific_name ORDER BY timestamp
                            ) as overall_rank,
                            MIN(timestamp) OVER (
                                PARTITION BY scientific_name
                            ) as first_ever_detection
                        FROM detections
                    ),
                    filtered_detections AS (
                        SELECT
                            d.*,
                            COALESCE(s.english_name, d.common_name) as ioc_english_name,
                            COALESCE(
                                t.common_name,
                                w.common_name,
                                s.english_name,
                                d.common_name
                            ) as translated_name,
                            s.family,
                            s.genus,
                            s.order_name,
                            adr.overall_rank,
                            adr.first_ever_detection
                        FROM detections d
                        JOIN all_detections_ranked adr
                            ON d.id = adr.id
                            AND d.scientific_name = adr.scientific_name
                            AND d.timestamp = adr.timestamp
                        LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                        LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                            AND t.language_code = :language_code
                        LEFT JOIN wikidata.translations w
                            ON w.avibase_id = (
                                SELECT i.avibase_id
                                FROM ioc.species i
                                WHERE i.scientific_name = d.scientific_name
                            )
                            AND w.language_code = :language_code
                        {where_clause}
                    ),
                    period_first AS (
                        SELECT
                            scientific_name,
                            MIN(timestamp) as first_period_detection
                        FROM detections
                        {time_where_clause}
                        GROUP BY scientific_name
                    )
                    SELECT
                        fd.id,
                        fd.species_tensor,
                        fd.scientific_name,
                        fd.common_name,
                        fd.confidence,
                        fd.timestamp,
                        fd.audio_file_id,
                        fd.latitude,
                        fd.longitude,
                        fd.species_confidence_threshold,
                        fd.week,
                        fd.sensitivity_setting,
                        fd.overlap,
                        fd.ioc_english_name,
                        fd.translated_name,
                        fd.family,
                        fd.genus,
                        fd.order_name,
                        CASE WHEN fd.overall_rank = 1 THEN 1 ELSE 0 END as is_first_ever,
                        CASE
                            WHEN fd.timestamp = pf.first_period_detection THEN 1
                            ELSE 0
                        END as is_first_in_period,
                        fd.first_ever_detection,
                        pf.first_period_detection
                    FROM filtered_detections fd
                    LEFT JOIN period_first pf ON fd.scientific_name = pf.scientific_name
                    ORDER BY fd.{"timestamp" if "timestamp" in order_by else order_by}
                        {"DESC" if order_desc else "ASC"}
                    {pagination_clause}
                """
                )
            else:
                # Standard query without window functions
                # Safe: WHERE/ORDER clauses use pre-defined fragments, user data is parameterized
                query_sql = text(  # nosemgrep
                    f"""
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
                            w.common_name,
                            s.english_name,
                            d.common_name
                        ) as translated_name,
                        s.family,
                        s.genus,
                        s.order_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                        AND t.language_code = :language_code
                    LEFT JOIN wikidata.translations w
                        ON w.avibase_id = (
                            SELECT i.avibase_id
                            FROM ioc.species i
                            WHERE i.scientific_name = d.scientific_name
                        )
                        AND w.language_code = :language_code
                    {where_clause}
                    {order_clause}
                    {pagination_clause}
                """
                )
        else:
            # Simplified query when species databases are not available (e.g., in tests)
            # Safe: WHERE/ORDER clauses use pre-defined fragments, user data is parameterized
            query_sql = text(  # nosemgrep
                f"""
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
                    d.common_name as ioc_english_name,
                    d.common_name as translated_name,
                    NULL as family,
                    NULL as genus,
                    NULL as order_name
                FROM detections d
                {where_clause}
                {order_clause}
                {pagination_clause}
            """
            )

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

            # Build DetectionWithTaxa with optional first detection fields
            detection_with_taxa = DetectionWithTaxa(
                detection=detection,
                ioc_english_name=result.ioc_english_name,  # type: ignore[attr-defined]
                translated_name=result.translated_name,  # type: ignore[attr-defined]
                family=result.family,  # type: ignore[attr-defined]
                genus=result.genus,  # type: ignore[attr-defined]
                order_name=result.order_name,  # type: ignore[attr-defined]
            )

            # Add first detection fields if they exist in the result
            if hasattr(result, "is_first_ever"):
                detection_with_taxa.is_first_ever = bool(result.is_first_ever)  # type: ignore[attr-defined]
            if hasattr(result, "is_first_in_period"):
                detection_with_taxa.is_first_in_period = bool(result.is_first_in_period)  # type: ignore[attr-defined]
            if hasattr(result, "first_ever_detection"):
                detection_with_taxa.first_ever_detection = self._parse_timestamp(
                    result.first_ever_detection
                )  # type: ignore[attr-defined]
            if hasattr(result, "first_period_detection"):
                detection_with_taxa.first_period_detection = self._parse_timestamp(
                    result.first_period_detection
                )  # type: ignore[attr-defined]

            detection_data_list.append(detection_with_taxa)

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
                    .order_by(desc("count"), Detection.scientific_name)
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

    async def count_by_date(self, species: str | None = None) -> dict[str, int]:
        """Count detections by date with optional species filter.

        Args:
            species: Optional scientific name to filter by

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to detection counts
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
                results = result.fetchall()
                if not results:
                    return {}
                # Convert tuple results to dict - row[0] is date, row[1] is count
                return {row[0]: int(row[1]) for row in results}
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Error counting by date")
                raise

    async def query_detections_with_first_detection_info(
        self,
        *,
        species: str | list[str] | None = None,
        family: str | None = None,
        genus: str | None = None,
        start_date: dt | None = None,
        end_date: dt | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int | None = 100,
        offset: int = 0,
        order_by: str = "timestamp",
        order_desc: bool = True,
    ) -> list[DetectionWithTaxa]:
        """Query detections with first detection flags using window functions.

        Adds two boolean fields to each detection:
        - is_first_ever: True if this is the first ever detection of this species
        - is_first_in_period: True if this is the first detection of this species in the
          selected period
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                # Build WHERE clause and parameters
                where_clause, params = self._build_where_clause_and_params(
                    limit=limit,
                    offset=offset,
                    start_date=start_date,
                    end_date=end_date,
                    scientific_name_filter=species,
                    family_filter=family,
                    genus_filter=genus,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                )

                # Main query with window functions for first detection flags
                query_sql = text(  # nosemgrep
                    f"""
                    WITH detection_ranks AS (
                        SELECT
                            d.*,
                            s.english_name as ioc_english_name,
                            s.family,
                            s.genus,
                            s.order_name,
                            COALESCE(
                                t.common_name,
                                w.common_name,
                                s.english_name
                            ) as translated_name,
                            ROW_NUMBER() OVER (
                                PARTITION BY d.scientific_name ORDER BY d.timestamp
                            ) as overall_rank,
                            ROW_NUMBER() OVER (
                                PARTITION BY d.scientific_name
                                ORDER BY CASE
                                    WHEN d.timestamp >= :start_date THEN d.timestamp
                                    ELSE NULL
                                END
                            ) as period_rank
                        FROM detections d
                        LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                        LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                            AND t.language_code = :language_code
                        LEFT JOIN wikidata.translations w
                            ON w.avibase_id = (
                                SELECT i.avibase_id
                                FROM ioc.species i
                                WHERE i.scientific_name = d.scientific_name
                            )
                            AND w.language_code = :language_code
                        {where_clause}
                    )
                    SELECT
                        *,
                        CASE WHEN overall_rank = 1 THEN 1 ELSE 0 END as is_first_ever,
                        CASE
                            WHEN period_rank = 1 AND timestamp >= :start_date THEN 1
                            ELSE 0
                        END as is_first_in_period
                    FROM detection_ranks
                    ORDER BY {order_by} {"DESC" if order_desc else "ASC"}
                    LIMIT :limit OFFSET :offset
                    """
                )

                result = await session.execute(query_sql, params)
                results = list(result.mappings())

                # Build DetectionWithTaxa objects from results
                detections = []
                for row in results:
                    # Create base Detection object
                    detection = Detection(
                        id=row["id"],
                        species_tensor=row["species_tensor"],
                        scientific_name=row["scientific_name"],
                        common_name=row["common_name"],
                        confidence=row["confidence"],
                        timestamp=row["timestamp"],
                        audio_file_id=row["audio_file_id"],
                        latitude=row.get("latitude"),
                        longitude=row.get("longitude"),
                        species_confidence_threshold=row.get("species_confidence_threshold"),
                        week=row.get("week"),
                        sensitivity_setting=row.get("sensitivity_setting"),
                        overlap=row.get("overlap"),
                        weather_timestamp=row.get("weather_timestamp"),
                        weather_latitude=row.get("weather_latitude"),
                        weather_longitude=row.get("weather_longitude"),
                        hour_epoch=row.get("hour_epoch"),
                    )

                    # Build DetectionWithTaxa with taxonomy and first detection info
                    detection_with_taxa = DetectionWithTaxa(
                        detection=detection,
                        ioc_english_name=row.get("ioc_english_name"),
                        translated_name=row.get("translated_name"),
                        family=row.get("family"),
                        genus=row.get("genus"),
                        order_name=row.get("order_name"),
                        is_first_ever=bool(row.get("is_first_ever")),
                        is_first_in_period=bool(row.get("is_first_in_period")),
                    )
                    detections.append(detection_with_taxa)

                return detections

            finally:
                await self.species_database.detach_all_from_session(session)

    async def get_species_with_first_detections(
        self,
        since: dt | None = None,
        family_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get species summary with first detection timestamps using window functions.

        Args:
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family

        Returns:
            List of species summary dictionaries with first detection info
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                where_clause = "WHERE 1=1"
                params: dict[str, Any] = {"language_code": self.config.language}

                if since:
                    where_clause += " AND d.timestamp >= :since"
                    params["since"] = since

                if family_filter:
                    where_clause += " AND s.family = :family"
                    params["family"] = family_filter

                # Query with window functions for first detections
                query_sql = text(  # nosemgrep
                    f"""
                    WITH ranked_detections AS (
                        SELECT
                            d.scientific_name,
                            d.timestamp,
                            d.confidence,
                            s.english_name as ioc_english_name,
                            s.family,
                            s.genus,
                            s.order_name,
                            COALESCE(
                                t.common_name,
                                w.common_name,
                                s.english_name
                            ) as translated_name,
                            ROW_NUMBER() OVER (
                                PARTITION BY d.scientific_name ORDER BY d.timestamp
                            ) as detection_rank,
                            MIN(d.timestamp) OVER (
                                PARTITION BY d.scientific_name
                            ) as first_ever_detection,
                            COUNT(*) OVER (PARTITION BY d.scientific_name) as detection_count,
                            AVG(d.confidence) OVER (
                                PARTITION BY d.scientific_name
                            ) as avg_confidence,
                            MAX(d.timestamp) OVER (
                                PARTITION BY d.scientific_name
                            ) as latest_detection
                        FROM detections d
                        LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                        LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                            AND t.language_code = :language_code
                        LEFT JOIN wikidata.translations w
                            ON w.avibase_id = (
                                SELECT i.avibase_id
                                FROM ioc.species i
                                WHERE i.scientific_name = d.scientific_name
                            )
                            AND w.language_code = :language_code
                        {where_clause}
                    ),
                    period_first_detections AS (
                        SELECT
                            scientific_name,
                            MIN(timestamp) as first_period_detection
                        FROM detections d
                        {where_clause}
                        GROUP BY scientific_name
                    )
                    SELECT
                        rd.scientific_name,
                        rd.detection_count,
                        rd.avg_confidence,
                        rd.latest_detection,
                        rd.first_ever_detection,
                        pfd.first_period_detection,
                        rd.ioc_english_name,
                        rd.translated_name,
                        rd.family,
                        rd.genus,
                        rd.order_name,
                        COALESCE(rd.translated_name, rd.ioc_english_name) as best_common_name
                    FROM ranked_detections rd
                    JOIN period_first_detections pfd ON rd.scientific_name = pfd.scientific_name
                    WHERE rd.detection_rank = 1
                    ORDER BY rd.first_ever_detection ASC
                    """
                )

                result = await session.execute(query_sql, params)
                results = list(result.mappings())

                species_summary = [
                    {
                        "scientific_name": result["scientific_name"],
                        "detection_count": result["detection_count"],
                        "avg_confidence": round(float(result["avg_confidence"]), 3),
                        "latest_detection": self._parse_timestamp(result["latest_detection"])
                        if result["latest_detection"]
                        else None,
                        "first_ever_detection": self._parse_timestamp(
                            result["first_ever_detection"]
                        )
                        if result["first_ever_detection"]
                        else None,
                        "first_period_detection": self._parse_timestamp(
                            result["first_period_detection"]
                        )
                        if result["first_period_detection"]
                        else None,
                        "ioc_english_name": result["ioc_english_name"],
                        "translated_name": result["translated_name"],
                        "family": result["family"],
                        "genus": result["genus"],
                        "order_name": result["order_name"],
                        "best_common_name": result["translated_name"] or result["ioc_english_name"],
                    }
                    for result in results
                ]

                return species_summary

            finally:
                await self.species_database.detach_all_from_session(session)

    # Ecological Analysis Methods

    async def get_species_counts_by_period(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        temporal_resolution: str = "daily",  # "hourly", "daily", "weekly"
    ) -> list[dict]:
        """Get species counts grouped by time period.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            temporal_resolution: Time grouping - "hourly", "daily", or "weekly"

        Returns:
            List of dicts with period and species_counts (dict of species->count)
        """
        async with self.core_database.get_async_db() as session:
            # Determine grouping based on resolution
            if temporal_resolution == "hourly":
                # Group by hour using strftime
                date_trunc = func.strftime("%Y-%m-%d %H:00:00", Detection.timestamp)
                period_format = "%Y-%m-%d %H:00"
            elif temporal_resolution == "weekly":
                # Group by week (Sunday as start)
                date_trunc = func.date(Detection.timestamp, "weekday 0", "-6 days")
                period_format = "%Y-W%W"
            else:  # daily
                date_trunc = func.date(Detection.timestamp)
                period_format = "%Y-%m-%d"

            # Get species counts per period
            query = (
                select(
                    date_trunc.label("period"),
                    Detection.scientific_name,
                    func.count(Detection.id).label("count"),
                )
                .where(
                    and_(
                        Detection.timestamp >= start_date,
                        Detection.timestamp <= end_date,
                    )
                )
                .group_by(date_trunc, Detection.scientific_name)
                .order_by(date_trunc)
            )

            result = await session.execute(query)
            rows = result.all()

            # Group by period
            periods = defaultdict(lambda: defaultdict(int))
            for row in rows:
                periods[row.period][row.scientific_name] = row.count

            # Return raw data for calculation in AnalyticsManager
            return [
                {
                    "period": period.strftime(period_format)
                    if hasattr(period, "strftime")
                    else str(period),
                    "species_counts": dict(species_counts),
                }
                for period, species_counts in periods.items()
            ]

    async def get_detections_for_accumulation(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[tuple[datetime.datetime, str]]:
        """Get detection data for species accumulation analysis.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period

        Returns:
            List of (timestamp, scientific_name) tuples in chronological order
        """
        async with self.core_database.get_async_db() as session:
            query = (
                select(Detection.timestamp, Detection.scientific_name)
                .where(
                    and_(
                        Detection.timestamp >= start_date,
                        Detection.timestamp <= end_date,
                    )
                )
                .order_by(Detection.timestamp)
            )

            result = await session.execute(query)
            return result.all()

    async def get_species_counts_for_periods(
        self,
        periods: list[tuple[datetime.datetime, datetime.datetime]],
    ) -> list[dict[str, int]]:
        """Get species counts for multiple time periods.

        Args:
            periods: List of (start_date, end_date) tuples

        Returns:
            List of dicts mapping species name to count for each period
        """
        async with self.core_database.get_async_db() as session:
            period_data = []

            for start_date, end_date in periods:
                query = (
                    select(
                        Detection.scientific_name,
                        func.count(Detection.id).label("count"),
                    )
                    .where(
                        and_(
                            Detection.timestamp >= start_date,
                            Detection.timestamp <= end_date,
                        )
                    )
                    .group_by(Detection.scientific_name)
                )

                result = await session.execute(query)
                species_counts = {row[0]: row[1] for row in result}
                period_data.append(species_counts)

            return period_data

    async def get_species_sets_by_window(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        window_size: timedelta,
    ) -> list[dict]:
        """Get species sets for sliding time windows.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            window_size: Size of sliding window

        Returns:
            List of dicts with period_start, period_end, and species set
        """
        async with self.core_database.get_async_db() as session:
            windows = []
            current_date = start_date

            while current_date + window_size <= end_date:
                window_end = current_date + window_size

                query = (
                    select(Detection.scientific_name)
                    .distinct()
                    .where(
                        and_(
                            Detection.timestamp >= current_date,
                            Detection.timestamp < window_end,
                        )
                    )
                )

                result = await session.execute(query)
                species = {row[0] for row in result}

                windows.append(
                    {
                        "period_start": current_date.isoformat(),
                        "period_end": window_end.isoformat(),
                        "species": list(species),
                    }
                )

                current_date += window_size

            return windows

    async def get_weather_correlations(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> dict:
        """Get detection counts with weather data for correlation analysis.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period

        Returns:
            Dictionary with hourly detection counts and weather variables
        """
        async with self.core_database.get_async_db() as session:
            # Check if hour_epoch columns exist and are populated
            # If not, fall back to string-based JOIN (slower)
            check_query = text("SELECT hour_epoch FROM detections LIMIT 1")
            try:
                await session.execute(check_query)
                use_optimized = True
            except Exception:
                use_optimized = False

            if use_optimized:
                # Optimized query using integer hour_epoch for 256x speedup
                query = (
                    select(
                        Detection.hour_epoch,
                        func.datetime(
                            func.coalesce(Detection.hour_epoch, 0) * 3600, "unixepoch"
                        ).label("hour"),
                        func.count(Detection.id).label("detection_count"),
                        func.count(func.distinct(Detection.scientific_name)).label("species_count"),
                        func.avg(Weather.temperature).label("temperature"),
                        func.avg(Weather.humidity).label("humidity"),
                        func.avg(Weather.pressure).label("pressure"),
                        func.avg(Weather.wind_speed).label("wind_speed"),
                        func.avg(Weather.precipitation).label("precipitation"),
                    )
                    .select_from(Detection)
                    .outerjoin(
                        Weather,
                        Detection.hour_epoch == Weather.hour_epoch,
                    )
                    .where(
                        and_(
                            Detection.timestamp >= start_date,
                            Detection.timestamp <= end_date,
                        )
                    )
                    .group_by(Detection.hour_epoch)
                    .order_by(Detection.hour_epoch)
                )
            else:
                # Fallback to original string-based JOIN (slower but works without migration)
                query = (
                    select(
                        func.strftime("%Y-%m-%d %H:00", Detection.timestamp).label("hour"),
                        func.count(Detection.id).label("detection_count"),
                        func.count(func.distinct(Detection.scientific_name)).label("species_count"),
                        func.avg(Weather.temperature).label("temperature"),
                        func.avg(Weather.humidity).label("humidity"),
                        func.avg(Weather.pressure).label("pressure"),
                        func.avg(Weather.wind_speed).label("wind_speed"),
                        func.avg(Weather.precipitation).label("precipitation"),
                    )
                    .select_from(Detection)
                    .outerjoin(
                        Weather,
                        func.strftime("%Y-%m-%d %H:00:00", Detection.timestamp)
                        == func.strftime("%Y-%m-%d %H:00:00", Weather.timestamp),
                    )
                    .where(
                        and_(
                            Detection.timestamp >= start_date,
                            Detection.timestamp <= end_date,
                        )
                    )
                    .group_by(func.strftime("%Y-%m-%d %H:00", Detection.timestamp))
                    .order_by("hour")
                )

            result = await session.execute(query)
            rows = result.all()

            data = {
                "hours": [],
                "detection_counts": [],
                "species_counts": [],
                "temperature": [],
                "humidity": [],
                "pressure": [],
                "wind_speed": [],
                "precipitation": [],
            }

            for row in rows:
                data["hours"].append(row.hour)
                data["detection_counts"].append(row.detection_count)
                data["species_counts"].append(row.species_count)
                data["temperature"].append(row.temperature)
                data["humidity"].append(row.humidity)
                data["pressure"].append(row.pressure)
                data["wind_speed"].append(row.wind_speed)
                data["precipitation"].append(row.precipitation)

            return data

    def _build_best_recordings_count_query(
        self,
        where_clause: str,
        species: str | None,
        family: str | None,
        per_species_limit: int | None,
    ) -> TextClause:
        """Build count query for best recordings based on filter type."""
        if species:
            # Simple count for single species - no ranking needed
            if family:
                return text(  # nosemgrep
                    f"""
                    SELECT COUNT(*) as total
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    WHERE {where_clause}
                    """
                )
            else:
                return text(  # nosemgrep
                    f"""
                    SELECT COUNT(*) as total
                    FROM detections d
                    WHERE {where_clause}
                    """
                )
        elif per_species_limit is None:
            # No per-species limit - count all matching detections
            if family:
                return text(  # nosemgrep
                    f"""
                    SELECT COUNT(*) as total
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    WHERE {where_clause}
                    """
                )
            else:
                return text(  # nosemgrep
                    f"""
                    SELECT COUNT(*) as total
                    FROM detections d
                    WHERE {where_clause}
                    """
                )
        elif family:
            # Need ranking for family filter with per-species limit
            return text(  # nosemgrep
                f"""
                WITH ranked_detections AS (
                    SELECT
                        d.scientific_name,
                        ROW_NUMBER() OVER (
                            PARTITION BY d.scientific_name
                            ORDER BY d.confidence DESC, d.timestamp DESC
                        ) as rank_within_species
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    WHERE {where_clause}
                )
                SELECT COUNT(*) as total
                FROM ranked_detections
                WHERE rank_within_species <= :per_species_limit
                """
            )
        else:
            # Default case with ranking
            return text(  # nosemgrep
                f"""
                WITH ranked_detections AS (
                    SELECT
                        d.scientific_name,
                        ROW_NUMBER() OVER (
                            PARTITION BY d.scientific_name
                            ORDER BY d.confidence DESC, d.timestamp DESC
                        ) as rank_within_species
                    FROM detections d
                    WHERE {where_clause}
                )
                SELECT COUNT(*) as total
                FROM ranked_detections
                WHERE rank_within_species <= :per_species_limit
                """
            )

    def _build_best_recordings_data_query(
        self,
        where_clause: str,
        species: str | None,
        family: str | None,
        per_species_limit: int | None,
    ) -> TextClause:
        """Build data query for best recordings based on filter type."""
        if species:
            # For specific species, skip ranking - just filter directly
            return text(  # nosemgrep
                f"""
                SELECT
                    d.id,
                    d.scientific_name,
                    d.common_name,
                    d.confidence,
                    d.timestamp,
                    d.audio_file_id,
                    s.family,
                    s.order_name,
                    COALESCE(
                        t.common_name,
                        w.common_name,
                        s.english_name,
                        d.common_name
                    ) AS translated_name
                FROM detections d
                LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                    AND t.language_code = :language_code
                LEFT JOIN wikidata.translations w
                    ON w.avibase_id = (
                        SELECT i.avibase_id
                        FROM ioc.species i
                        WHERE i.scientific_name = d.scientific_name
                    )
                    AND w.language_code = :language_code
                WHERE {where_clause}
                ORDER BY d.confidence DESC, d.timestamp DESC
                LIMIT :limit OFFSET :offset
                """
            )
        elif per_species_limit is None:
            # No per-species limit - get all detections directly
            return text(  # nosemgrep
                f"""
                SELECT
                    d.id,
                    d.scientific_name,
                    d.common_name,
                    d.confidence,
                    d.timestamp,
                    d.audio_file_id,
                    s.family,
                    s.order_name,
                    COALESCE(
                        t.common_name,
                        w.common_name,
                        s.english_name,
                        d.common_name
                    ) AS translated_name
                FROM detections d
                LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                    AND t.language_code = :language_code
                LEFT JOIN wikidata.translations w
                    ON w.avibase_id = (
                        SELECT i.avibase_id
                        FROM ioc.species i
                        WHERE i.scientific_name = d.scientific_name
                    )
                    AND w.language_code = :language_code
                WHERE {where_clause}
                ORDER BY d.confidence DESC, d.timestamp DESC
                LIMIT :limit OFFSET :offset
                """
            )
        else:
            # Use ranking to limit per species
            join_clause = (
                "LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name" if family else ""
            )
            ranked_cte = f"""
                WITH ranked_detections AS (
                    SELECT
                        d.id,
                        d.scientific_name,
                        d.common_name,
                        d.confidence,
                        d.timestamp,
                        d.audio_file_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY d.scientific_name
                            ORDER BY d.confidence DESC, d.timestamp DESC
                        ) as rank_within_species
                    FROM detections d
                    {join_clause}
                    WHERE {where_clause}
                )"""
            return text(  # nosemgrep
                ranked_cte
                + """
                SELECT
                    rd.id,
                    rd.scientific_name,
                    rd.common_name,
                    rd.confidence,
                    rd.timestamp,
                    rd.audio_file_id,
                    s.family,
                    s.order_name,
                    COALESCE(
                        t.common_name,
                        w.common_name,
                        s.english_name,
                        rd.common_name
                    ) AS translated_name
                FROM ranked_detections rd
                LEFT JOIN ioc.species s ON rd.scientific_name = s.scientific_name
                LEFT JOIN ioc.translations t ON s.avibase_id = t.avibase_id
                    AND t.language_code = :language_code
                LEFT JOIN wikidata.translations w
                    ON w.avibase_id = (
                        SELECT i.avibase_id
                        FROM ioc.species i
                        WHERE i.scientific_name = rd.scientific_name
                    )
                    AND w.language_code = :language_code
                WHERE rd.rank_within_species <= :per_species_limit
                ORDER BY rd.confidence DESC, rd.timestamp DESC
                LIMIT :limit OFFSET :offset
                """
            )

    def _create_detection_with_taxa_from_row(self, row: BestRecordingRow) -> DetectionWithTaxa:
        """Create DetectionWithTaxa from a database row result."""
        # Build species_tensor from scientific_name and common_name
        species_tensor = f"{row.scientific_name}_{row.common_name}"

        detection = Detection(
            id=UUID(row.id),
            scientific_name=row.scientific_name,
            common_name=row.common_name,
            confidence=row.confidence,
            timestamp=self._parse_timestamp(row.timestamp),
            audio_file_id=UUID(row.audio_file_id) if row.audio_file_id else None,
            # Set defaults for required but unused fields
            species_tensor=species_tensor,
            latitude=None,
            longitude=None,
            species_confidence_threshold=None,
            week=None,
            sensitivity_setting=None,
            overlap=None,
        )

        return DetectionWithTaxa(
            detection=detection,
            translated_name=(
                row.translated_name if hasattr(row, "translated_name") else row.common_name
            ),
            family=row.family if hasattr(row, "family") else None,
            order_name=row.order_name if hasattr(row, "order_name") else None,
            # Set defaults for unused fields
            ioc_english_name=None,
            genus=None,
        )

    def _build_best_recordings_filter_conditions(
        self,
        species: str | None,
        genus: str | None,
        family: str | None,
        min_confidence: float,
        params: dict[str, Any],
    ) -> list[str]:
        """Build filter conditions for best recordings query."""
        filter_conditions = ["d.confidence >= :min_confidence"]

        if species:
            filter_conditions.append("d.scientific_name = :species")
            params["species"] = species
        elif genus:
            # For genus, match the first part of the scientific name
            filter_conditions.append("d.scientific_name LIKE :genus_pattern")
            params["genus_pattern"] = f"{genus} %"
        elif family:
            # Family requires joining with IOC species table
            filter_conditions.append("s.family = :family")
            params["family"] = family

        return filter_conditions

    async def query_best_recordings_per_species(
        self,
        per_species_limit: int | None = 5,
        min_confidence: float = 0.5,
        language_code: str = "en",
        page: int = 1,
        per_page: int = 50,
        family: str | None = None,
        genus: str | None = None,
        species: str | None = None,
    ) -> tuple[list[DetectionWithTaxa], int]:
        """Get best recordings with an optional limit per species.

        Uses SQL window functions to rank detections within each species by confidence
        and returns only the top N per species. When filtering by a specific species,
        pass None for per_species_limit to get all recordings.

        Args:
            per_species_limit: Maximum number of detections per species (None = no limit)
            min_confidence: Minimum confidence threshold
            language_code: Language code for translations
            page: Page number for pagination (1-indexed)
            per_page: Number of items per page
            family: Optional family filter
            genus: Optional genus filter
            species: Optional species (scientific name) filter

        Returns:
            Tuple of (list of DetectionWithTaxa objects, total count)
        """
        async with self.core_database.get_async_db() as session:
            await self.species_database.attach_all_to_session(session)
            try:
                # Calculate offset for pagination
                offset = (page - 1) * per_page

                # Build base parameters
                params: dict[str, Any] = {
                    "min_confidence": min_confidence,
                    "language_code": language_code,
                    "limit": per_page,
                    "offset": offset,
                }

                # Only add per_species_limit if we have one and not filtering by specific species
                if per_species_limit is not None and not species:
                    params["per_species_limit"] = per_species_limit

                # Build filter conditions
                filter_conditions = self._build_best_recordings_filter_conditions(
                    species, genus, family, min_confidence, params
                )
                where_clause = " AND ".join(filter_conditions)

                # Build and execute count query
                count_sql = self._build_best_recordings_count_query(
                    where_clause, species, family, per_species_limit
                )

                # Use only the parameters needed for count query
                count_params: dict[str, Any] = {"min_confidence": min_confidence}
                if per_species_limit is not None and not species:
                    count_params["per_species_limit"] = per_species_limit
                if species:
                    count_params["species"] = species
                if genus:
                    count_params["genus_pattern"] = params["genus_pattern"]
                if family:
                    count_params["family"] = family

                count_result = await session.execute(count_sql, count_params)
                total_count = count_result.scalar() or 0

                # Build and execute data query
                query_sql = self._build_best_recordings_data_query(
                    where_clause, species, family, per_species_limit
                )

                result = await session.execute(query_sql, params)
                results = result.fetchall()

                detection_data_list = []
                for row in results:
                    detection_with_taxa = self._create_detection_with_taxa_from_row(row)
                    detection_data_list.append(detection_with_taxa)

                return detection_data_list, total_count
            finally:
                await self.species_database.detach_all_from_session(session)
