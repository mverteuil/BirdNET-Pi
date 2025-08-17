"""Tests for ConfigManager."""

import pytest
import yaml

from birdnetpi.config import BirdNETConfig, ConfigManager


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_load_config_creates_default_if_missing(self, path_resolver):
        """Test that default config is created if file doesn't exist."""
        # Ensure config file doesn't exist
        config_path = path_resolver.get_birdnetpi_config_path()
        if config_path.exists():
            config_path.unlink()

        manager = ConfigManager(path_resolver)
        config = manager.load()

        # Should create a default config
        assert isinstance(config, BirdNETConfig)
        assert config.config_version == "2.0.0"
        assert config.site_name == "BirdNET-Pi"

        # Should save the default config
        assert config_path.exists()

    def test_load_config_with_existing_file(self, path_resolver):
        """Test loading an existing config file."""
        # Create a config file
        config_path = path_resolver.get_birdnetpi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = {
            "config_version": "2.0.0",
            "site_name": "Test Site",
            "latitude": 45.0,
            "longitude": -75.0,
            "species_confidence_threshold": 0.05,
            "sensitivity_setting": 1.5,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        manager = ConfigManager(path_resolver)
        config = manager.load()

        assert config.site_name == "Test Site"
        assert config.latitude == 45.0
        assert config.longitude == -75.0
        assert config.species_confidence_threshold == 0.05
        assert config.sensitivity_setting == 1.5

    def test_migrate_config_from_1_9_0(self, path_resolver):
        """Test migrating config from version 1.9.0 to 2.0.0."""
        # Create an old-style config file
        config_path = path_resolver.get_birdnetpi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        old_config_data = {
            "config_version": "1.9.0",
            "site_name": "Old Site",
            "latitude": 40.0,
            "longitude": -80.0,
            "sf_thresh": 0.03,  # Old field name
            "sensitivity": 1.25,  # Old field name
        }

        with open(config_path, "w") as f:
            yaml.dump(old_config_data, f)

        manager = ConfigManager(path_resolver)
        config = manager.load()

        # Check that fields were migrated
        assert config.config_version == "2.0.0"
        assert config.site_name == "Old Site"
        assert config.species_confidence_threshold == 0.03  # Renamed from sf_thresh
        assert config.sensitivity_setting == 1.25  # Renamed from sensitivity

        # Check that new fields have defaults
        assert config.privacy_threshold == 10.0
        assert config.enable_mqtt is False
        assert config.enable_webhooks is False

    def test_save_config(self, path_resolver):
        """Test saving a config to file."""
        manager = ConfigManager(path_resolver)
        config = BirdNETConfig(
            site_name="Save Test",
            latitude=50.0,
            longitude=-70.0,
        )

        manager.save(config)

        # Load the saved file and verify
        config_path = path_resolver.get_birdnetpi_config_path()
        with open(config_path) as f:
            saved_data = yaml.safe_load(f)

        assert saved_data["site_name"] == "Save Test"
        assert saved_data["latitude"] == 50.0
        assert saved_data["longitude"] == -70.0
        assert saved_data["config_version"] == "2.0.0"

    def test_backup_creation(self, path_resolver):
        """Test that backups are created when saving over existing config."""
        config_path = path_resolver.get_birdnetpi_config_path()
        backup_path = config_path.with_suffix(".yaml.backup")
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial config
        original_data = {"config_version": "2.0.0", "site_name": "Original"}
        with open(config_path, "w") as f:
            yaml.dump(original_data, f)

        manager = ConfigManager(path_resolver)
        new_config = BirdNETConfig(site_name="Updated")
        manager.save(new_config)

        # Check backup was created with original content
        assert backup_path.exists()
        with open(backup_path) as f:
            backup_data = yaml.safe_load(f)
        assert backup_data["site_name"] == "Original"

        # Check main file has new content
        with open(config_path) as f:
            new_data = yaml.safe_load(f)
        assert new_data["site_name"] == "Updated"

    def test_invalid_version_raises_error(self, path_resolver):
        """Test that invalid config version raises an error."""
        config_path = path_resolver.get_birdnetpi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        invalid_config = {
            "config_version": "99.0.0",  # Non-existent version
            "site_name": "Test",
        }

        with open(config_path, "w") as f:
            yaml.dump(invalid_config, f)

        manager = ConfigManager(path_resolver)
        with pytest.raises(ValueError, match="Unknown config version"):
            manager.load()

    def test_partial_config_gets_defaults(self, path_resolver):
        """Test that missing fields are filled with defaults."""
        config_path = path_resolver.get_birdnetpi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        partial_config = {
            "config_version": "2.0.0",
            "site_name": "Partial Test",
            # Missing many required fields
        }

        with open(config_path, "w") as f:
            yaml.dump(partial_config, f)

        manager = ConfigManager(path_resolver)
        config = manager.load()

        # Should have defaults for missing fields
        assert config.site_name == "Partial Test"
        assert config.latitude == 0.0  # Default
        assert config.longitude == 0.0  # Default
        assert config.species_confidence_threshold == 0.03  # Default
        assert config.sensitivity_setting == 1.25  # Default
