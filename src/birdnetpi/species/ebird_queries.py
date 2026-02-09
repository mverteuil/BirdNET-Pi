"""Query service for eBird regional confidence with neighbor search and temporal adjustments.

This service handles complex eBird queries including H3 neighbor search, multi-resolution
fallback, and temporal data from monthly frequency tables.
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

# Data resolutions available in region packs (finest to coarsest)
# Must match DATA_RESOLUTIONS in ebd-pack-builder
DATA_RESOLUTIONS = [5, 4, 2]


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
        with multi-resolution fallback. The region packs contain data at resolutions
        5, 4, and 2. We search:
        1. User's cell + neighbors at resolution 5 (finest)
        2. Parent cells at resolution 4 (medium, as fallback)
        3. Parent cells at resolution 2 (coarse, as fallback)

        Resolution penalties are already baked into confidence_boost at build time.

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
            - resolution: H3 resolution of the matched data
            - region_pack: Name of the region pack used (filled by caller)
            None if species not found in any searched ring
        """
        # Convert lat/lon to H3 cell at configured resolution
        user_h3_cell = h3.latlng_to_cell(latitude, longitude, config.h3_resolution)

        # Build set of cells to search at resolution 5 (finest)
        res5_cells = {user_h3_cell}
        if config.neighbor_search_enabled and config.neighbor_search_max_rings > 0:
            for k in range(1, config.neighbor_search_max_rings + 1):
                res5_cells.update(h3.grid_ring(user_h3_cell, k))

        # Build search cells including parent cells at coarser resolutions
        # This allows fallback to res 4 and res 2 data when res 5 data is sparse
        all_cells_int: list[int] = []

        for cell in res5_cells:
            all_cells_int.append(int(cell, 16))

        # Add parent cells at coarser resolutions (4 and 2) for the user's location
        # We only need parent cells for the user's exact location, not all neighbors
        for resolution in DATA_RESOLUTIONS:
            if resolution < config.h3_resolution:
                parent_cell = h3.cell_to_parent(user_h3_cell, resolution)
                all_cells_int.append(int(parent_cell, 16))

        # Remove duplicates while preserving order
        seen = set()
        neighbor_cells_int = []
        for cell in all_cells_int:
            if cell not in seen:
                seen.add(cell)
                neighbor_cells_int.append(cell)

        # Query with temporal data from monthly table
        # Use LEFT JOIN so we get results even if monthly data is missing
        # Order by resolution DESC so we prefer finer resolution data
        if month is not None and config.use_monthly_frequency:
            stmt = (
                text(
                    """
                SELECT
                    gs.h3_cell,
                    gs.resolution,
                    gs.confidence_tier,
                    gs.confidence_boost as base_boost,
                    gs.yearly_frequency,
                    gs.quality_score,
                    sl.scientific_name,
                    gsm.frequency as month_frequency
                FROM ebird.grid_species gs
                JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
                LEFT JOIN ebird.grid_species_monthly gsm
                    ON gs.h3_cell = gsm.h3_cell
                    AND gs.resolution = gsm.resolution
                    AND gs.avibase_id = gsm.avibase_id
                    AND gsm.month = :month
                WHERE gs.h3_cell IN :neighbor_cells
                AND sl.scientific_name = :scientific_name
                ORDER BY gs.resolution DESC
            """
                )
                .bindparams(bindparam("neighbor_cells", expanding=True))
                .bindparams(bindparam("scientific_name"))
                .bindparams(bindparam("month"))
            )

            result = await session.execute(
                stmt,
                {
                    "neighbor_cells": neighbor_cells_int,
                    "scientific_name": scientific_name,
                    "month": month,
                },
            )
        else:
            stmt = (
                text(
                    """
                SELECT
                    gs.h3_cell,
                    gs.resolution,
                    gs.confidence_tier,
                    gs.confidence_boost as base_boost,
                    gs.yearly_frequency,
                    gs.quality_score,
                    sl.scientific_name,
                    NULL as month_frequency
                FROM ebird.grid_species gs
                JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
                WHERE gs.h3_cell IN :neighbor_cells
                AND sl.scientific_name = :scientific_name
                ORDER BY gs.resolution DESC
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

        # Find best match: prefer finest resolution, then closest distance
        # Parent cells at coarser resolutions are considered distance 0 at their resolution
        best_match = None
        best_resolution = -1
        min_distance = float("inf")

        # Precompute parent cells to identify them as "distance 0" at their resolution
        parent_cells_int = {
            int(h3.cell_to_parent(user_h3_cell, res), 16): res
            for res in DATA_RESOLUTIONS
            if res < config.h3_resolution
        }
        parent_cells_int[int(user_h3_cell, 16)] = config.h3_resolution

        for row in rows:
            row_resolution = row.resolution  # type: ignore[attr-defined]
            row_cell_int = row.h3_cell  # type: ignore[attr-defined]

            # Calculate distance: parent cells at coarser resolutions are distance 0
            if row_cell_int in parent_cells_int:
                distance = 0
            elif row_resolution == config.h3_resolution:
                # Same resolution as user cell, can compute grid distance
                matched_cell_hex = hex(row_cell_int)[2:]
                distance = h3.grid_distance(user_h3_cell, matched_cell_hex)
            else:
                # Neighbor cell at a different resolution - shouldn't happen with current logic
                # but handle gracefully by treating as far away
                distance = float("inf")

            # Priority: highest resolution first, then closest distance
            if row_resolution > best_resolution:
                best_match = row
                best_resolution = row_resolution
                min_distance = distance
            elif row_resolution == best_resolution and distance < min_distance:
                best_match = row
                min_distance = distance

        if not best_match:
            return None

        # Extract data from best match
        matched_cell_hex = hex(best_match.h3_cell)[2:]  # type: ignore[attr-defined]
        matched_resolution = best_match.resolution  # type: ignore[attr-defined]
        base_boost = float(best_match.base_boost)  # type: ignore[attr-defined]
        tier = best_match.confidence_tier  # type: ignore[attr-defined]
        quality_score = float(best_match.quality_score or 0.5)  # type: ignore[attr-defined]

        # Calculate distance-based multiplier (only for res-5 neighbor cells)
        # Parent cells at coarser resolutions already have resolution penalty baked into boost
        if matched_resolution == config.h3_resolution and config.neighbor_search_enabled:
            ring_multiplier = 1.0 - (min_distance * config.neighbor_boost_decay_per_ring)
        else:
            # Coarser resolution or exact match - no additional ring penalty
            ring_multiplier = 1.0

        # Quality multiplier based on observation quality
        quality_multiplier = config.quality_multiplier_base + (
            config.quality_multiplier_range * quality_score
        )

        # Temporal adjustments using monthly frequency data
        temporal_multiplier = 1.0
        if month is not None and config.use_monthly_frequency:
            month_freq = best_match.month_frequency  # type: ignore[attr-defined]

            # Use monthly frequency if available, otherwise fall back to yearly_frequency
            if month_freq is not None:
                freq = float(month_freq)
            elif best_match.yearly_frequency is not None:  # type: ignore[attr-defined]
                freq = float(best_match.yearly_frequency)  # type: ignore[attr-defined]
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
            "Found %s in cell %s (res: %d, distance: %d rings, base: %.2f, quality: %.2f, "
            "ring_mult: %.2f, quality_mult: %.2f, temporal_mult: %.2f → final: %.2f)",
            scientific_name,
            matched_cell_hex,
            matched_resolution,
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
            "ring_distance": int(min_distance) if min_distance != float("inf") else 0,
            "resolution": matched_resolution,
            "region_pack": None,  # To be filled by caller
        }
