"""Service for checking eBird region pack status."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from birdnetpi.releases.registry_service import RegistryService

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
        self.registry_service = RegistryService(path_resolver)

    def check_status(self) -> dict[str, object]:
        """Check region pack status.

        Region packs are auto-selected based on latitude/longitude.
        This checks if the correct pack exists for the configured location.

        Returns:
            Dictionary with status information:
            - has_pack: Whether any region pack exists locally
            - pack_count: Number of available local packs
            - location_set: Whether lat/lon coordinates are configured
            - correct_pack_installed: Whether correct pack for location is installed
            - recommended_pack: Region ID of recommended pack (if location set)
            - needs_attention: Whether user should take action
            - message: Human-readable status message
        """
        # Check if location is configured
        lat = self.config.latitude
        lon = self.config.longitude
        location_set = not (lat == 0.0 and lon == 0.0)

        # Get list of locally available packs
        available_packs = self.list_available_packs()
        pack_count = len(available_packs)
        has_pack = pack_count > 0

        # If location is set, find the recommended pack
        recommended_pack = None
        correct_pack_installed = False

        if location_set:
            try:
                region_info = self.registry_service.find_pack_for_coordinates(lat, lon)
                if region_info:
                    recommended_pack = region_info.region_id
                    # Check if we have the correct pack locally
                    recommended_file = f"{region_info.region_id}.db"
                    correct_pack_installed = any(
                        p.name == recommended_file for p in available_packs
                    )
            except Exception as e:
                logger.warning("Failed to check registry for location (%s, %s): %s", lat, lon, e)

        # Build status response
        if not location_set:
            return {
                "has_pack": has_pack,
                "pack_count": pack_count,
                "location_set": False,
                "correct_pack_installed": False,
                "recommended_pack": None,
                "needs_attention": True,
                "message": "Set your location in Settings to enable regional species filtering.",
            }

        if not recommended_pack:
            return {
                "has_pack": has_pack,
                "pack_count": pack_count,
                "location_set": True,
                "correct_pack_installed": False,
                "recommended_pack": None,
                "needs_attention": True,
                "message": f"No region pack available for coordinates ({lat}, {lon}). "
                "This location may not be covered yet.",
            }

        if correct_pack_installed:
            return {
                "has_pack": True,
                "pack_count": pack_count,
                "location_set": True,
                "correct_pack_installed": True,
                "recommended_pack": recommended_pack,
                "needs_attention": False,
                "message": None,
            }

        # Recommended pack not installed
        return {
            "has_pack": has_pack,
            "pack_count": pack_count,
            "location_set": True,
            "correct_pack_installed": False,
            "recommended_pack": recommended_pack,
            "needs_attention": True,
            "message": f"Download recommended pack '{recommended_pack}' for your location.",
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
