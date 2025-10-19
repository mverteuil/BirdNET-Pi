"""Service for checking eBird region pack status."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from birdnetpi.config import BirdNETConfig
    from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class RegionPackStatusService:
    """Service for checking eBird region pack availability and location match."""

    def __init__(self, path_resolver: PathResolver, config: BirdNETConfig):
        """Initialize region pack status service.

        Args:
            path_resolver: File path resolver for pack locations
            config: BirdNET configuration
        """
        self.path_resolver = path_resolver
        self.config = config

    def check_status(self) -> dict[str, object]:
        """Check region pack status.

        Region packs are auto-selected based on latitude/longitude.
        This checks if ANY pack exists and if location is set.

        Returns:
            Dictionary with status information:
            - has_pack: Whether any region pack exists
            - pack_count: Number of available packs
            - location_set: Whether lat/lon coordinates are configured
            - needs_attention: Whether user should take action
            - message: Human-readable status message
        """
        # Check if location is configured (not default)
        location_set = not (self.config.latitude == 0.0 and self.config.longitude == 0.0)

        # Get list of available packs
        available_packs = self.list_available_packs()
        pack_count = len(available_packs)
        has_pack = pack_count > 0

        # If no packs available
        if not has_pack:
            if location_set:
                return {
                    "has_pack": False,
                    "pack_count": 0,
                    "location_set": True,
                    "needs_attention": True,
                    "message": "No region pack installed for your location. "
                    "Visit Updates to download a region pack for your coordinates.",
                }
            else:
                msg = "Set your location in Settings to enable regional species filtering."
                return {
                    "has_pack": False,
                    "pack_count": 0,
                    "location_set": False,
                    "needs_attention": True,
                    "message": msg,
                }

        # Packs available
        if location_set:
            return {
                "has_pack": True,
                "pack_count": pack_count,
                "location_set": True,
                "needs_attention": False,
                "message": None,
            }
        else:
            return {
                "has_pack": True,
                "pack_count": pack_count,
                "location_set": False,
                "needs_attention": True,
                "message": "Region pack available but location not set. "
                "Set your location for accurate regional filtering.",
            }

    def _extract_region_from_pack_name(self, pack_name: str) -> str | None:
        """Extract region identifier from pack name.

        Args:
            pack_name: Pack name like "na-east-coast-2025.08" or "na-east-coast-2025.08.db"

        Returns:
            Region identifier like "na-east-coast", or None if parsing fails
        """
        # Remove .db extension if present
        pack_name = pack_name.replace(".db", "")

        # Pattern: region-YYYY.MM (month release) or region-YYYY-MM-DD (date release)
        # Extract everything before the date pattern
        match = re.match(r"^(.+?)-\d{4}[.-]\d{2}", pack_name)
        if match:
            return match.group(1)

        return None

    def list_available_packs(self) -> list[Path]:
        """List all available region pack files.

        Returns:
            List of Path objects for .db files in the database directory
        """
        db_dir = self.path_resolver.data_dir / "database"
        if not db_dir.exists():
            return []

        # Find all .db files that match region pack naming pattern
        # Pattern: name-YYYY.MM.db or name-YYYY-MM-DD.db
        packs = []
        for db_file in db_dir.glob("*.db"):
            # Skip main databases
            if db_file.name in [
                "birdnetpi.db",
                "ioc_reference.db",
                "avibase_database.db",
                "patlevin_database.db",
            ]:
                continue

            # Check if it matches region pack pattern
            if re.match(r"^.+-\d{4}[.-]\d{2}", db_file.stem):
                packs.append(db_file)

        return sorted(packs)
