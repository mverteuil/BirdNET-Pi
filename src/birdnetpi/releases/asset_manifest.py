"""Central registry of BirdNET-Pi asset definitions.

This module provides a single source of truth for defining what constitutes
a BirdNET-Pi asset (models, databases) that should be preserved during
test cleanup and included in releases.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from birdnetpi.system.path_resolver import PathResolver


class AssetType(StrEnum):
    """Types of assets in the BirdNET-Pi system."""

    MODEL = "model"
    DATABASE = "database"


@dataclass(frozen=True)
class Asset:
    """Definition of a BirdNET-Pi asset.

    Attributes:
        name: Human-readable name for the asset
        path_method: Name of the PathResolver method that returns this asset's path
        description: Detailed description of the asset
        asset_type: Type of asset (model or database)
        is_directory: Whether this asset is a directory (True) or file (False)
        required: Whether this asset is required for basic functionality
    """

    name: str
    path_method: str
    description: str
    asset_type: AssetType
    is_directory: bool = False
    required: bool = True


class AssetManifest:
    """Central registry of BirdNET-Pi asset definitions.

    This class provides a single source of truth for all BirdNET-Pi assets,
    used by release management, update management, and test cleanup.
    """

    # Define all BirdNET-Pi assets
    _ASSETS: ClassVar[list[Asset]] = [
        Asset(
            name="BirdNET Models",
            path_method="get_models_dir",
            description="BirdNET TensorFlow Lite models for bird identification",
            asset_type=AssetType.MODEL,
            is_directory=True,
            required=True,
        ),
        Asset(
            name="IOC Reference Database",
            path_method="get_ioc_database_path",
            description="IOC World Bird Names with translations (24 languages, CC-BY-4.0)",
            asset_type=AssetType.DATABASE,
            is_directory=False,
            required=True,
        ),
        Asset(
            name="Wikidata Reference Database",
            path_method="get_wikidata_database_path",
            description="Wikidata bird names (57 languages, CC0), images, conservation status",
            asset_type=AssetType.DATABASE,
            is_directory=False,
            required=True,
        ),
    ]

    @classmethod
    def get_all_assets(cls) -> list[Asset]:
        """Get all defined assets.

        Returns:
            List of all Asset definitions
        """
        return list(cls._ASSETS)

    @classmethod
    def get_required_assets(cls) -> list[Asset]:
        """Get only required assets.

        Returns:
            List of Asset definitions marked as required
        """
        return [asset for asset in cls._ASSETS if asset.required]

    @classmethod
    def get_optional_assets(cls) -> list[Asset]:
        """Get only optional assets.

        Returns:
            List of Asset definitions marked as optional (not required)
        """
        return [asset for asset in cls._ASSETS if not asset.required]

    @classmethod
    def get_asset_paths(cls, path_resolver: PathResolver) -> dict[str, Path]:
        """Get a mapping of asset names to their paths.

        Args:
            path_resolver: PathResolver instance to get actual paths

        Returns:
            Dictionary mapping asset names to Path objects
        """
        paths = {}
        for asset in cls._ASSETS:
            # Get the method from PathResolver and call it
            method = getattr(path_resolver, asset.path_method)
            paths[asset.name] = method()
        return paths

    @classmethod
    def get_protected_paths(cls, path_resolver: PathResolver) -> list[Path]:
        """Get list of all paths that should be protected during cleanup.

        Args:
            path_resolver: PathResolver instance to get actual paths

        Returns:
            List of Path objects that should be preserved
        """
        protected = []
        for asset in cls._ASSETS:
            method = getattr(path_resolver, asset.path_method)
            path = method()
            protected.append(path)

            # For directories, also protect their parent to avoid accidental deletion
            # But only if parent is not the data_dir itself
            if asset.is_directory and path.parent and path.parent != path_resolver.data_dir:
                protected.append(path.parent)

        # Always protect the database directory itself
        protected.append(path_resolver.get_database_dir())

        return protected

    @classmethod
    def is_protected_path(cls, path: Path, path_resolver: PathResolver) -> bool:
        """Check if a given path is a protected asset.

        Args:
            path: Path to check
            path_resolver: PathResolver instance to get actual paths

        Returns:
            True if the path is a protected asset or inside a protected directory
        """
        path = path.resolve()
        protected_paths = cls.get_protected_paths(path_resolver)

        for protected in protected_paths:
            protected = protected.resolve()
            # Check if path matches exactly or is inside a protected directory
            if path == protected or protected in path.parents:
                return True

        return False

    @classmethod
    def get_assets_by_type(cls, asset_type: AssetType) -> list[Asset]:
        """Get all assets of a specific type.

        Args:
            asset_type: Type of assets to retrieve

        Returns:
            List of Asset definitions of the specified type
        """
        return [asset for asset in cls._ASSETS if asset.asset_type == asset_type]

    @classmethod
    def get_asset_by_name(cls, name: str) -> Asset | None:
        """Get a specific asset by its name.

        Args:
            name: Name of the asset to retrieve

        Returns:
            Asset definition if found, None otherwise
        """
        for asset in cls._ASSETS:
            if asset.name == name:
                return asset
        return None

    @classmethod
    def get_release_assets(cls, path_resolver: PathResolver) -> list[tuple[Path, Path, str]]:
        """Get asset information formatted for release management.

        Returns a list of tuples suitable for creating ReleaseAsset objects.

        Args:
            path_resolver: PathResolver instance to get actual paths

        Returns:
            List of tuples (source_path, target_path, description)
        """
        release_assets = []

        for asset in cls._ASSETS:
            method = getattr(path_resolver, asset.path_method)
            source_path = method()

            # Determine target path based on asset type
            # We need to handle both development and production paths
            try:
                # Try to get relative path from data_dir
                rel_path = source_path.relative_to(path_resolver.data_dir)
                target_path = Path("data") / rel_path
            except ValueError:
                # In development, paths might not be under data_dir
                # Use a standard structure based on asset type
                if asset.is_directory:
                    target_path = Path("data/models")
                elif "ioc" in asset.name.lower():
                    target_path = Path("data/database/ioc_reference.db")
                elif "wikidata" in asset.name.lower():
                    target_path = Path("data/database/wikidata_reference.db")
                else:
                    # Fallback - use the source path's name
                    target_path = Path("data") / source_path.name

            release_assets.append((source_path, target_path, asset.description))

        return release_assets
