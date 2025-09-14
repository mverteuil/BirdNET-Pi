"""Registry for configuration versions."""

import importlib
from pathlib import Path
from typing import Any, Protocol


class ConfigVersion(Protocol):
    """Protocol for configuration version handlers."""

    version: str
    previous_version: str | None

    def apply_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply version-specific defaults to config."""
        ...

    def upgrade_from_previous(self, config: dict[str, Any]) -> dict[str, Any]:
        """Upgrade config from previous version."""
        ...

    def validate(self, config: dict[str, Any]) -> list[str]:
        """Validate config for this version."""
        ...


class VersionRegistry:
    """Manages configuration versions and upgrade paths."""

    def __init__(self):
        """Initialize the version registry."""
        self._versions: dict[str, ConfigVersion] = {}
        self._load_versions()

    def _load_versions(self) -> None:
        """Dynamically load all version modules."""
        versions_dir = Path(__file__).parent

        for version_file in sorted(versions_dir.glob("v*.py")):
            module_name = version_file.stem
            # Safe: Loading version modules from controlled application directory, not user input
            module = importlib.import_module(  # nosemgrep
                f"birdnetpi.config.versions.{module_name}"
            )

            # Find the version class in the module
            for attr_name in dir(module):
                if attr_name.startswith("ConfigVersion_"):
                    version_class = getattr(module, attr_name)
                    version_instance = version_class()
                    self._versions[version_instance.version] = version_instance

    def get_version(self, version_string: str) -> ConfigVersion:
        """Get the version handler for a specific version.

        Args:
            version_string: Version string (e.g., "2.5.0")

        Returns:
            ConfigVersion: Version handler for the specified version

        Raises:
            ValueError: If version is not found
        """
        if version_string not in self._versions:
            raise ValueError(f"Unknown config version: {version_string}")

        return self._versions[version_string]

    def get_upgrade_path(self, from_version: str, to_version: str) -> list[ConfigVersion]:
        """Get the upgrade path between two versions.

        Args:
            from_version: Starting version
            to_version: Target version

        Returns:
            list[ConfigVersion]: List of version handlers to apply in order
        """
        if from_version == to_version:
            return []

        path = []

        # Build upgrade path by following previous_version links
        version_chain = self._build_version_chain()

        if from_version not in version_chain:
            # Unknown starting version, start from oldest
            from_version = min(version_chain.keys())

        if to_version not in version_chain:
            # Unknown target version, use latest
            to_version = max(version_chain.keys())

        # Find all versions between from and to
        for version in sorted(version_chain.keys()):
            if version > from_version and version <= to_version:
                path.append(self._versions[version])

        return path

    def _build_version_chain(self) -> dict[str, str | None]:
        """Build a map of version -> previous_version.

        Returns:
            dict: Mapping of version strings to their previous versions
        """
        chain = {}
        for version_str, version_obj in self._versions.items():
            chain[version_str] = version_obj.previous_version
        return chain

    def get_current_version(self) -> ConfigVersion:
        """Get the current/latest version handler.

        Returns:
            ConfigVersion: Handler for the latest version
        """
        if not self._versions:
            raise ValueError("No configuration versions found")

        latest = max(self._versions.keys())
        return self._versions[latest]
