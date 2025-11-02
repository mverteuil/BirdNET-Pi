"""Query service for eBird regional confidence with neighbor search and temporal adjustments.

This service handles complex eBird queries including H3 neighbor search and temporal
data from monthly/quarterly/yearly tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import h3
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from birdnetpi.config.models import EBirdFilterConfig

logger = logging.getLogger(__name__)


class EBirdQueryService:
    """Service for complex eBird regional confidence queries."""

    async def get_confidence_with_neighbors(  # noqa: C901
        self,
        session: AsyncSession,
        scientific_name: str,
        latitude: float,
        longitude: float,
        config: EBirdFilterConfig,
        month: int | None = None,
    ) -> dict[str, Any] | None:
        """Get confidence data for a species with neighbor search and temporal adjustments.

        Searches the user's H3 cell and surrounding neighbors for species data,
        applying distance-based confidence adjustments and temporal factors from
        monthly/quarterly/yearly tables.

        Args:
            session: SQLAlchemy async session with eBird database attached
            scientific_name: Scientific name of the species
            latitude: User's latitude
            longitude: User's longitude
            config: eBird filtering configuration
            month: Current month (1-12) for temporal adjustments, None to disable

        Returns:
            Dictionary with confidence data if found:
            - confidence_boost: Final calculated boost (1.0-2.0)
            - confidence_tier: Tier (common/uncommon/rare/vagrant)
            - h3_cell: Matched H3 cell (hex string)
            - ring_distance: Distance in rings from user location (0=exact match)
            - region_pack: Name of the region pack used (filled by caller)
            None if species not found in any searched ring
        """
        # Convert lat/lon to H3 cell
        user_h3_cell = h3.latlng_to_cell(latitude, longitude, config.h3_resolution)

        # Calculate neighbor cells to search
        neighbor_cells = {user_h3_cell}  # Start with exact match
        if config.neighbor_search_enabled and config.neighbor_search_max_rings > 0:
            for k in range(1, config.neighbor_search_max_rings + 1):
                neighbor_cells.update(h3.grid_ring(user_h3_cell, k))

        # Convert to integers for database query
        neighbor_cells_int = [int(cell, 16) for cell in neighbor_cells]

        # Query with temporal data from all tables (monthly, quarterly, yearly)
        # Use LEFT JOINs so we get results even if temporal data is missing
        if month is not None and config.use_monthly_frequency:
            # Calculate quarter from month (1-3 -> Q1, 4-6 -> Q2, etc.)
            quarter = ((month - 1) // 3) + 1

            stmt = (
                text(
                    """
                SELECT
                    gs.h3_cell,
                    gs.confidence_tier,
                    gs.confidence_boost as base_boost,
                    gs.yearly_frequency,
                    gs.quality_score,
                    sl.scientific_name,
                    gsm.frequency as month_frequency,
                    gsq.frequency as quarter_frequency,
                    gsy.frequency as year_frequency
                FROM ebird.grid_species gs
                JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
                LEFT JOIN ebird.grid_species_monthly gsm
                    ON gs.h3_cell = gsm.h3_cell
                    AND gs.avibase_id = gsm.avibase_id
                    AND gsm.month = :month
                LEFT JOIN ebird.grid_species_quarterly gsq
                    ON gs.h3_cell = gsq.h3_cell
                    AND gs.avibase_id = gsq.avibase_id
                    AND gsq.quarter = :quarter
                LEFT JOIN ebird.grid_species_yearly gsy
                    ON gs.h3_cell = gsy.h3_cell
                    AND gs.avibase_id = gsy.avibase_id
                WHERE gs.h3_cell IN :neighbor_cells
                AND sl.scientific_name = :scientific_name
            """
                )
                .bindparams(bindparam("neighbor_cells", expanding=True))
                .bindparams(bindparam("scientific_name"))
                .bindparams(bindparam("month"))
                .bindparams(bindparam("quarter"))
            )

            result = await session.execute(
                stmt,
                {
                    "neighbor_cells": neighbor_cells_int,
                    "scientific_name": scientific_name,
                    "month": month,
                    "quarter": quarter,
                },
            )
        else:
            stmt = (
                text(
                    """
                SELECT
                    gs.h3_cell,
                    gs.confidence_tier,
                    gs.confidence_boost as base_boost,
                    gs.yearly_frequency,
                    gs.quality_score,
                    sl.scientific_name,
                    NULL as month_frequency,
                    NULL as quarter_frequency,
                    NULL as year_frequency
                FROM ebird.grid_species gs
                JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
                WHERE gs.h3_cell IN :neighbor_cells
                AND sl.scientific_name = :scientific_name
            """
                )
                .bindparams(bindparam("neighbor_cells", expanding=True))
                .bindparams(bindparam("scientific_name"))
            )

            result = await session.execute(
                stmt, {"neighbor_cells": neighbor_cells_int, "scientific_name": scientific_name}
            )

        rows = result.fetchall()

        if not rows:
            logger.debug(
                "Species %s not found in any searched H3 cells (user cell: %s, rings: %d)",
                scientific_name,
                user_h3_cell,
                config.neighbor_search_max_rings if config.neighbor_search_enabled else 0,
            )
            return None

        # Find closest match (minimum ring distance)
        closest_match = None
        min_distance = float("inf")

        for row in rows:
            matched_cell_hex = hex(row.h3_cell)[2:]  # type: ignore[attr-defined]
            distance = h3.grid_distance(user_h3_cell, matched_cell_hex)

            if distance < min_distance:
                min_distance = distance
                closest_match = row

        if not closest_match:
            return None

        # Extract data from closest match
        matched_cell_hex = hex(closest_match.h3_cell)[2:]  # type: ignore[attr-defined]
        base_boost = float(closest_match.base_boost)  # type: ignore[attr-defined]
        tier = closest_match.confidence_tier  # type: ignore[attr-defined]
        quality_score = float(closest_match.quality_score or 0.5)  # type: ignore[attr-defined]

        # Calculate distance-based multiplier
        ring_multiplier = 1.0 - (
            min_distance * config.neighbor_boost_decay_per_ring
            if config.neighbor_search_enabled
            else 0
        )

        # Quality multiplier based on observation quality
        quality_multiplier = config.quality_multiplier_base + (
            config.quality_multiplier_range * quality_score
        )

        # Temporal adjustments using all available temporal data
        temporal_multiplier = 1.0
        if month is not None and config.use_monthly_frequency:
            month_freq = closest_match.month_frequency  # type: ignore[attr-defined]
            quarter_freq = closest_match.quarter_frequency  # type: ignore[attr-defined]

            # Use most specific available frequency data
            if month_freq is not None:
                freq = float(month_freq)
            elif quarter_freq is not None:
                freq = float(quarter_freq)
            else:
                freq = None

            if freq is not None:
                if freq == 0:
                    # Species absent in this period
                    temporal_multiplier = config.absence_penalty_factor
                elif freq > 0.5:
                    # Peak season
                    temporal_multiplier = config.peak_season_boost
                elif freq < 0.1:
                    # Off season
                    temporal_multiplier = config.off_season_penalty

        # Calculate final confidence boost
        final_boost = base_boost * ring_multiplier * quality_multiplier * temporal_multiplier

        logger.debug(
            "Found %s in cell %s (distance: %d rings, base: %.2f, quality: %.2f, "
            "ring_mult: %.2f, quality_mult: %.2f, temporal_mult: %.2f → final: %.2f)",
            scientific_name,
            matched_cell_hex,
            min_distance,
            base_boost,
            quality_score,
            ring_multiplier,
            quality_multiplier,
            temporal_multiplier,
            final_boost,
        )

        return {
            "confidence_boost": final_boost,
            "confidence_tier": tier,
            "h3_cell": matched_cell_hex,
            "ring_distance": int(min_distance),
            "region_pack": None,  # To be filled by caller
        }
