"""Service for querying eBird regional confidence data.

This service provides access to eBird regional pack databases for location-aware
confidence filtering. It handles database attachment/detachment and basic queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import h3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)

# Data resolutions available in region packs (finest to coarsest)
# Must match DATA_RESOLUTIONS in ebd-pack-builder
DATA_RESOLUTIONS = [5, 4, 2]


class EBirdRegionService:
    """Service for eBird regional pack database session management."""

    def __init__(self, path_resolver: PathResolver):
        """Initialize eBird region service.

        Args:
            path_resolver: File path resolver for database locations
        """
        self.path_resolver = path_resolver

    async def attach_to_session(self, session: AsyncSession, region_pack_name: str) -> None:
        """Attach eBird pack database to session for queries.

        Args:
            session: SQLAlchemy async session (typically from main detections database)
            region_pack_name: Name of the region pack (e.g., "africa-east-2025.08")
        """
        pack_path = self.path_resolver.get_ebird_pack_path(region_pack_name)

        if not pack_path.exists():
            logger.warning("eBird pack database not found: %s", pack_path)
            raise FileNotFoundError(f"eBird pack not found: {pack_path}")

        # Safe: paths come from PathResolver, not user input
        attach_sql = text(f"ATTACH DATABASE '{pack_path}' AS ebird")  # nosemgrep
        await session.execute(attach_sql)
        logger.debug("Attached eBird pack database: %s", region_pack_name)

    async def detach_from_session(self, session: AsyncSession) -> None:
        """Detach eBird pack database from session.

        Args:
            session: SQLAlchemy async session
        """
        try:
            # Safe: database alias is hardcoded, not user input
            await session.execute(text("DETACH DATABASE ebird"))  # nosemgrep
            logger.debug("Detached eBird pack database")
        except Exception as e:
            logger.debug("Error detaching eBird database (may not be attached): %s", e)

    async def get_species_confidence_tier(
        self,
        session: AsyncSession,
        scientific_name: str,
        h3_cell: str,
    ) -> str | None:
        """Get confidence tier for a species at a specific H3 cell.

        Args:
            session: SQLAlchemy async session with eBird database attached
            scientific_name: Scientific name of the species
            h3_cell: H3 cell index as hex string (e.g., "85283473fffffff")

        Returns:
            Confidence tier string ("common", "uncommon", "rare", "vagrant") or None if not found
        """
        # Convert hex string to integer for database query
        try:
            h3_cell_int = int(h3_cell, 16)
        except ValueError:
            logger.error("Invalid H3 cell format: %s", h3_cell)
            return None

        stmt = text("""
            SELECT gs.confidence_tier
            FROM ebird.grid_species gs
            JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
            WHERE gs.h3_cell = :h3_cell
            AND sl.scientific_name = :scientific_name
            ORDER BY gs.resolution DESC
        """)

        result = await session.execute(
            stmt, {"h3_cell": h3_cell_int, "scientific_name": scientific_name}
        )
        row = result.first()

        if row and row.confidence_tier:  # type: ignore[attr-defined]
            return row.confidence_tier  # type: ignore[attr-defined,no-any-return]

        return None

    async def get_confidence_boost(
        self,
        session: AsyncSession,
        scientific_name: str,
        h3_cell: str,
    ) -> float | None:
        """Get confidence boost multiplier for a species at a specific H3 cell.

        Args:
            session: SQLAlchemy async session with eBird database attached
            scientific_name: Scientific name of the species
            h3_cell: H3 cell index as hex string

        Returns:
            Confidence boost multiplier (1.0-2.0) or None if not found
        """
        try:
            h3_cell_int = int(h3_cell, 16)
        except ValueError:
            logger.error("Invalid H3 cell format: %s", h3_cell)
            return None

        stmt = text("""
            SELECT gs.confidence_boost
            FROM ebird.grid_species gs
            JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
            WHERE gs.h3_cell = :h3_cell
            AND sl.scientific_name = :scientific_name
            ORDER BY gs.resolution DESC
        """)

        result = await session.execute(
            stmt, {"h3_cell": h3_cell_int, "scientific_name": scientific_name}
        )
        row = result.first()

        if row and row.confidence_boost:  # type: ignore[attr-defined]
            return float(row.confidence_boost)  # type: ignore[attr-defined]

        return None

    async def is_species_in_region(
        self,
        session: AsyncSession,
        scientific_name: str,
        h3_cell: str,
    ) -> bool:
        """Check if a species is present in the eBird data for a specific H3 cell.

        Args:
            session: SQLAlchemy async session with eBird database attached
            scientific_name: Scientific name of the species
            h3_cell: H3 cell index as hex string

        Returns:
            True if species is found in the cell, False otherwise
        """
        tier = await self.get_species_confidence_tier(session, scientific_name, h3_cell)
        return tier is not None

    async def get_allowed_species_for_location(
        self,
        session: AsyncSession,
        h3_cell: str,
        strictness: str,
    ) -> set[str]:
        """Get set of allowed species for a location based on strictness level.

        This is used for site-wide filtering. Results should be cached for 24 hours.
        Searches the provided cell AND parent cells at coarser resolutions (4, 2)
        to find all species that pass the strictness filter.

        Args:
            session: SQLAlchemy async session with eBird database attached
            h3_cell: H3 cell index as hex string
            strictness: One of "vagrant", "rare", "uncommon", "common"

        Returns:
            Set of scientific names that pass the strictness filter
        """
        try:
            h3_cell_int = int(h3_cell, 16)
        except ValueError:
            logger.error("Invalid H3 cell format: %s", h3_cell)
            return set()

        # Get resolution of provided cell and compute parent cells at coarser resolutions
        cell_resolution = h3.get_resolution(h3_cell)
        cells_to_search = [h3_cell_int]

        for resolution in DATA_RESOLUTIONS:
            if resolution < cell_resolution:
                parent_cell = h3.cell_to_parent(h3_cell, resolution)
                cells_to_search.append(int(parent_cell, 16))

        # Build tier filter based on strictness
        if strictness == "vagrant":
            # Allow everything except vagrant
            tier_filter = "confidence_tier != 'vagrant'"
        elif strictness == "rare":
            # Allow uncommon and common
            tier_filter = "confidence_tier IN ('uncommon', 'common')"
        elif strictness == "uncommon":
            # Allow only common
            tier_filter = "confidence_tier = 'common'"
        elif strictness == "common":
            # Allow only common (same as uncommon for this purpose)
            tier_filter = "confidence_tier = 'common'"
        else:
            # Unknown strictness - allow all
            logger.warning("Unknown strictness level: %s, allowing all species", strictness)
            tier_filter = "1=1"

        # tier_filter is constructed from hardcoded values based on strictness parameter
        # For allowed species, we want any species that passes the filter at ANY resolution
        # (if it's common at res 5, it should be allowed even if data also exists at res 2)
        # Build parameter placeholders for cells list
        cell_placeholders = ", ".join(f":cell_{i}" for i in range(len(cells_to_search)))
        cell_params = {f"cell_{i}": cell for i, cell in enumerate(cells_to_search)}

        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        stmt = text(  # nosemgrep
            f"""
            SELECT DISTINCT sl.scientific_name
            FROM ebird.grid_species gs
            JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
            WHERE gs.h3_cell IN ({cell_placeholders})
            AND gs.{tier_filter}
        """
        )

        result = await session.execute(stmt, cell_params)

        # Extract scientific names into a set
        allowed_species = {row.scientific_name for row in result}  # type: ignore[attr-defined]

        logger.debug(
            "Found %d allowed species for cell %s (+ %d parent cells) with strictness %s",
            len(allowed_species),
            h3_cell,
            len(cells_to_search) - 1,
            strictness,
        )

        return allowed_species
