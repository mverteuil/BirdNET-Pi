"""Service for downloading and installing eBird region packs.

This module provides reusable functionality for downloading region packs
that can be used by both the CLI and background daemons.
"""

import gzip
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

from birdnetpi.releases.registry_service import RegionPackInfo, RegistryService
from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class RegionPackService:
    """Service for downloading and managing region packs."""

    def __init__(self, path_resolver: PathResolver) -> None:
        """Initialize the region pack service.

        Args:
            path_resolver: Path resolver for determining install locations.
        """
        self.path_resolver = path_resolver
        self.registry_service = RegistryService(path_resolver)

    def get_install_path(self, region_id: str) -> Path:
        """Get the installation path for a region pack.

        Args:
            region_id: The region identifier.

        Returns:
            Path where the region pack database should be installed.
        """
        db_dir = self.path_resolver.data_dir / "database"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / f"{region_id}.db"

    def is_installed(self, region_id: str) -> bool:
        """Check if a region pack is already installed.

        Args:
            region_id: The region identifier.

        Returns:
            True if the pack is installed, False otherwise.
        """
        return self.get_install_path(region_id).exists()

    def find_pack_for_coordinates(self, lat: float, lon: float) -> RegionPackInfo | None:
        """Find the appropriate region pack for given coordinates.

        Args:
            lat: Latitude.
            lon: Longitude.

        Returns:
            Region pack info or None if no pack covers the coordinates.
        """
        return self.registry_service.find_pack_for_coordinates(lat, lon)

    def download_and_install(
        self,
        region_pack: RegionPackInfo,
        force: bool = False,
        progress_callback: Callable[[float, float], None] | None = None,
    ) -> Path:
        """Download and install a region pack.

        Args:
            region_pack: The region pack info with download URL.
            force: If True, overwrite existing pack.
            progress_callback: Optional callback(downloaded_mb, total_mb) for progress.

        Returns:
            Path to the installed database file.

        Raises:
            ValueError: If pack has no download URL.
            FileExistsError: If pack exists and force is False.
            Exception: If download or extraction fails.
        """
        if not region_pack.download_url:
            raise ValueError(f"Region pack '{region_pack.region_id}' has no download URL")

        return self.download_from_url(
            region_id=region_pack.region_id,
            download_url=region_pack.download_url,
            size_mb=region_pack.total_size_mb,
            force=force,
            progress_callback=progress_callback,
        )

    def download_from_url(
        self,
        region_id: str,
        download_url: str,
        size_mb: float = 0,
        force: bool = False,
        progress_callback: Callable[[float, float], None] | None = None,
    ) -> Path:
        """Download and install a region pack from a direct URL.

        This method is used by daemons that receive download requests with
        minimal info (just region_id and URL) without the full RegionPackInfo.

        Args:
            region_id: The region identifier.
            download_url: Direct download URL for the .db.gz file.
            size_mb: Expected size in MB (for logging, 0 if unknown).
            force: If True, overwrite existing pack.
            progress_callback: Optional callback(downloaded_mb, total_mb) for progress.

        Returns:
            Path to the installed database file.

        Raises:
            FileExistsError: If pack exists and force is False.
            Exception: If download or extraction fails.
        """
        output_path = self.get_install_path(region_id)

        if output_path.exists() and not force:
            raise FileExistsError(f"Region pack '{region_id}' already installed at {output_path}")

        if size_mb > 0:
            logger.info("Downloading region pack '%s' (%.1f MB)", region_id, size_mb)
        else:
            logger.info("Downloading region pack '%s'", region_id)

        try:
            self._download_and_extract(download_url, output_path, progress_callback)

            logger.info(
                "Region pack '%s' installed successfully at %s",
                region_id,
                output_path,
            )
            return output_path

        except Exception:
            # Clean up partial download on failure
            if output_path.exists():
                output_path.unlink()
            temp_gz = output_path.with_suffix(".db.gz")
            if temp_gz.exists():
                temp_gz.unlink()
            raise

    def _download_and_extract(
        self,
        download_url: str,
        output_path: Path,
        progress_callback: Callable[[float, float], None] | None = None,
    ) -> None:
        """Download and extract a .db.gz file.

        Args:
            download_url: GitHub release asset download URL.
            output_path: Path where the .db file should be saved.
            progress_callback: Optional callback(downloaded_mb, total_mb) for progress.
        """
        logger.debug("Downloading from: %s", download_url)

        # Download the .db.gz file
        with urlopen(download_url, timeout=300) as response:  # nosemgrep
            total_size = int(response.headers.get("Content-Length", 0))
            total_mb = total_size / 1024 / 1024
            chunk_size = 8192
            downloaded = 0

            # Create a temporary file for the compressed download
            temp_gz = output_path.with_suffix(".db.gz")

            with open(temp_gz, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    # Report progress
                    if progress_callback and total_size > 0:
                        downloaded_mb = downloaded / 1024 / 1024
                        progress_callback(downloaded_mb, total_mb)

        logger.debug("Download complete, extracting...")

        # Extract the .db.gz file to .db
        with gzip.open(temp_gz, "rb") as f_in:
            with open(output_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Remove the temporary .gz file
        temp_gz.unlink()

        file_size_mb = output_path.stat().st_size / 1024 / 1024
        logger.debug("Extraction complete (%.1f MB)", file_size_mb)
