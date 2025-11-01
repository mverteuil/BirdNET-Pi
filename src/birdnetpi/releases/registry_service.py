"""Service for fetching and parsing eBird region pack registry."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.request import urlopen

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)

# Registry URL - points to the latest registry release
REGISTRY_URL = "https://github.com/mverteuil/birdnetpi-ebird-packs/releases/download/registry-2025.08/pack_registry_with_urls.json"
REGISTRY_CACHE_TTL = 3600  # 1 hour


class BoundingBox(BaseModel):
    """Geographic bounding box for a region."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class RegionPackInfo(BaseModel):
    """Information about a region pack from registry."""

    region_id: str
    release_name: str
    h3_cells: list[str]
    pack_count: int
    total_size_mb: float
    resolution: int
    center: dict[str, float]
    bbox: BoundingBox
    download_url: str | None = Field(None, description="GitHub release asset download URL")


class PackRegistry(BaseModel):
    """Complete pack registry structure."""

    version: str
    generated_at: datetime
    total_regions: int
    total_packs: int
    regions: list[RegionPackInfo]


class RegistryService:
    """Service for fetching and parsing region pack registry."""

    def __init__(self, path_resolver: PathResolver):
        """Initialize registry service.

        Args:
            path_resolver: Path resolver for cache location
        """
        self.path_resolver = path_resolver
        self.cache_path = path_resolver.data_dir / "cache" / "pack_registry.json"

    def fetch_registry(self, force_refresh: bool = False) -> PackRegistry:
        """Fetch region pack registry from GitHub or cache.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Parsed pack registry

        Raises:
            Exception: If fetch or parse fails
        """
        # Check cache first unless force refresh
        if not force_refresh and self.cache_path.exists():
            cache_age = datetime.now().timestamp() - self.cache_path.stat().st_mtime
            if cache_age < REGISTRY_CACHE_TTL:
                logger.info("Using cached registry (age: %.0f seconds)", cache_age)
                with open(self.cache_path) as f:
                    data = json.load(f)
                return PackRegistry(**data)

        # Fetch from GitHub
        logger.info("Fetching registry from %s", REGISTRY_URL)
        try:
            with urlopen(REGISTRY_URL, timeout=30) as response:  # nosemgrep
                data = json.loads(response.read())

            # Save to cache
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info("Registry fetched and cached successfully")
            return PackRegistry(**data)

        except Exception as e:
            logger.error("Failed to fetch registry: %s", e)
            # Try to use stale cache as fallback
            if self.cache_path.exists():
                logger.warning("Using stale cache as fallback")
                with open(self.cache_path) as f:
                    data = json.load(f)
                return PackRegistry(**data)
            raise

    def find_pack_for_coordinates(self, lat: float, lon: float) -> RegionPackInfo | None:
        """Find the appropriate region pack for given coordinates.

        If coordinates fall within multiple regions, returns the one whose
        center is closest to the coordinates.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Region pack info if found, None otherwise
        """
        registry = self.fetch_registry()

        # Find all packs whose bounding box contains the coordinates
        matching_regions = []
        for region in registry.regions:
            bbox = region.bbox
            if bbox.min_lat <= lat <= bbox.max_lat and bbox.min_lon <= lon <= bbox.max_lon:
                matching_regions.append(region)

        if not matching_regions:
            return None

        if len(matching_regions) == 1:
            return matching_regions[0]

        # Multiple matches - find the one with center closest to coordinates
        def distance_to_center(region: RegionPackInfo) -> float:
            """Calculate approximate distance from coordinates to region center."""
            center_lat = region.center["lat"]
            center_lon = region.center["lon"]
            # Simple Euclidean distance (good enough for comparison)
            return ((lat - center_lat) ** 2 + (lon - center_lon) ** 2) ** 0.5

        return min(matching_regions, key=distance_to_center)

    def list_all_packs(self) -> list[RegionPackInfo]:
        """List all available region packs from registry.

        Returns:
            List of all region pack info
        """
        registry = self.fetch_registry()
        return registry.regions
