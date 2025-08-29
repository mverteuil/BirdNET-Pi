"""Configuration management with version support."""

import logging
import shutil
from typing import Any

import yaml

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.config.versions import VersionRegistry
from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading, saving, and migration."""

    CURRENT_VERSION = "2.0.0"

    def __init__(self, path_resolver: PathResolver | None = None):
        """Initialize ConfigManager.

        Args:
            path_resolver: Optional PathResolver instance. If None, creates a new one.
        """
        self.path_resolver = path_resolver or PathResolver()
        self.registry = VersionRegistry()
        self.config_path = self.path_resolver.get_birdnetpi_config_path()
        self.template_path = self.path_resolver.get_config_template_path()

    def load(self) -> BirdNETConfig:
        """Load configuration with migration and validation.

        Returns:
            BirdNETConfig: Loaded and validated configuration
        """
        # Ensure config file exists
        self._ensure_config_exists()

        # Load raw config
        raw_config = self._read_yaml()

        # Get version and corresponding handler
        config_version = raw_config.get("config_version", "1.9.0")
        version_handler = self.registry.get_version(config_version)

        # Apply defaults for that version
        raw_config = version_handler.apply_defaults(raw_config)

        # Migrate to current version if needed
        if config_version != self.CURRENT_VERSION:
            raw_config = self._migrate_to_current(raw_config, config_version)

        # Validate final config
        current_handler = self.registry.get_version(self.CURRENT_VERSION)
        errors = current_handler.validate(raw_config)
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")

        # Create typed config object
        return self._create_config_object(raw_config)

    def save(self, config: BirdNETConfig) -> None:
        """Save configuration to file with backup.

        Args:
            config: Configuration to save

        Raises:
            PermissionError: If config file cannot be written
        """
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing config
        if self.config_path.exists():
            backup_path = self.config_path.with_suffix(".yaml.backup")
            try:
                shutil.copy2(self.config_path, backup_path)
            except PermissionError:
                logger.warning("Could not create backup at %s", backup_path)

        # Convert to dict and save
        config_dict = self._config_to_dict(config)
        config_yaml = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

        self.config_path.write_text(config_yaml)
        logger.info("Configuration saved successfully to %s", self.config_path)

    def reload(self) -> BirdNETConfig:
        """Reload configuration from disk.

        Returns:
            BirdNETConfig: Freshly loaded configuration
        """
        return self.load()

    def _ensure_config_exists(self) -> None:
        """Ensure config file exists, create from version defaults if needed."""
        if not self.config_path.exists():
            # Create config directory if needed
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Create config from current version defaults
            current_handler = self.registry.get_version(self.CURRENT_VERSION)
            config_with_defaults = current_handler.apply_defaults(
                {"config_version": self.CURRENT_VERSION}
            )

            # Save the config with defaults
            config_yaml = yaml.dump(config_with_defaults, default_flow_style=False, sort_keys=False)
            self.config_path.write_text(config_yaml)

    def _read_yaml(self) -> dict[str, Any]:
        """Read YAML config file.

        Returns:
            dict: Raw configuration dictionary
        """
        config_text = self.config_path.read_text()
        return yaml.safe_load(config_text) or {}

    def _migrate_to_current(self, raw_config: dict[str, Any], from_version: str) -> dict[str, Any]:
        """Migrate config to current version.

        Args:
            raw_config: Configuration to migrate
            from_version: Starting version

        Returns:
            dict: Migrated configuration
        """
        upgrade_path = self.registry.get_upgrade_path(from_version, self.CURRENT_VERSION)

        for version_handler in upgrade_path:
            raw_config = version_handler.upgrade_from_previous(raw_config)
            raw_config["config_version"] = version_handler.version

        return raw_config

    def _create_config_object(self, raw_config: dict[str, Any]) -> BirdNETConfig:
        """Create BirdNETConfig object from dictionary.

        Args:
            raw_config: Configuration dictionary

        Returns:
            BirdNETConfig: Typed configuration object
        """
        # Handle nested logging config
        if "logging" in raw_config and isinstance(raw_config["logging"], dict):
            from birdnetpi.config.models import LoggingConfig

            raw_config["logging"] = LoggingConfig(**raw_config["logging"])

        # Filter out any unexpected fields that might remain from incomplete migrations
        # Get the expected fields from BirdNETConfig using Pydantic's model_fields
        expected_fields = set(BirdNETConfig.model_fields.keys())

        # Only include fields that BirdNETConfig expects
        filtered_config = {k: v for k, v in raw_config.items() if k in expected_fields}

        # Log if any fields were filtered out (for debugging migration issues)
        unexpected_fields = set(raw_config.keys()) - expected_fields
        if unexpected_fields:
            logger.warning(
                "Filtered out unexpected config fields (likely from incomplete migration): %s",
                unexpected_fields,
            )

        return BirdNETConfig(**filtered_config)

    def _config_to_dict(self, config: BirdNETConfig) -> dict[str, Any]:
        """Convert BirdNETConfig to dictionary for serialization.

        Args:
            config: Configuration object

        Returns:
            dict: Configuration as dictionary
        """
        # Use Pydantic's model_dump() method for serialization
        return config.model_dump()
