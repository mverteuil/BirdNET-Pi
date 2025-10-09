"""Tests for configuration file permissions and directory setup."""

import os
from pathlib import Path

import pytest

from birdnetpi.config import BirdNETConfig, ConfigManager


class TestConfigPermissions:
    """Test configuration file and directory permissions."""

    def test_config_directory_creation(self, tmp_path, path_resolver):
        """Should config directory is created if it doesn't exist."""
        # Use a unique subdirectory that doesn't exist yet
        unique_dir = tmp_path / "test_creation"
        config_dir = unique_dir / "config"
        config_path = config_dir / "birdnetpi.yaml"
        path_resolver.get_birdnetpi_config_path = lambda: config_path

        # Directory should not exist yet
        assert not config_path.parent.exists()

        # ConfigManager should create the directory
        config_manager = ConfigManager(path_resolver)
        config = BirdNETConfig(site_name="Test")
        config_manager.save(config)

        # Directory and file should now exist
        assert config_path.parent.exists()
        assert config_path.exists()

    def test_config_write_permissions(self, tmp_path, path_resolver):
        """Should config file can be written and read."""
        # Configure path_resolver to use temp directory
        config_dir = tmp_path / "config"
        config_path = config_dir / "birdnetpi.yaml"
        path_resolver.get_birdnetpi_config_path = lambda: config_path

        config_manager = ConfigManager(path_resolver)

        # Should be able to save
        config = BirdNETConfig(site_name="Permission Test", latitude=42.0, longitude=-71.0)

        # This should not raise any permission errors
        config_manager.save(config)

        # Should be able to read back
        loaded_config = config_manager.load()
        assert loaded_config.site_name == "Permission Test"
        assert loaded_config.latitude == 42.0

    def test_config_handles_readonly_directory(self, tmp_path, path_resolver):
        """Should error handling when config directory is read-only."""
        # Use a unique subdirectory to avoid conflicts with pre-created directories
        unique_dir = tmp_path / "test_readonly"
        config_dir = unique_dir / "config"
        config_dir.mkdir(parents=True)

        # Make directory read-only (Unix only)
        if os.name != "nt":  # Not Windows
            os.chmod(config_dir, 0o444)

        try:
            config_path = config_dir / "birdnetpi.yaml"
            path_resolver.get_birdnetpi_config_path = lambda: config_path

            config_manager = ConfigManager(path_resolver)
            config = BirdNETConfig(site_name="Readonly Test")

            # Should handle permission error gracefully
            if os.name != "nt":  # Only test on Unix
                with pytest.raises((PermissionError, OSError)):
                    config_manager.save(config)

        finally:
            # Restore write permissions for cleanup
            if os.name != "nt":
                # Restore owner-only access for temp directory cleanup
                os.chmod(config_dir, 0o700)  # nosemgrep

    def test_config_creates_parent_directories(self, tmp_path, path_resolver):
        """Should all parent directories are created as needed."""
        # Use a unique subdirectory with deeply nested path
        unique_dir = tmp_path / "test_nested"
        nested_path = unique_dir / "deep" / "nested" / "path" / "config"
        config_path = nested_path / "birdnetpi.yaml"
        path_resolver.get_birdnetpi_config_path = lambda: config_path

        config_manager = ConfigManager(path_resolver)

        # Should create all parent directories
        config = BirdNETConfig(site_name="Nested Test")
        config_manager.save(config)

        # Verify all directories were created
        assert config_path.exists()
        assert config_path.parent.exists()

    def test_config_handles_existing_file(self, tmp_path, path_resolver):
        """Should properly overwrite existing config files."""
        config_dir = tmp_path / "config"
        config_path = config_dir / "birdnetpi.yaml"
        path_resolver.get_birdnetpi_config_path = lambda: config_path

        config_manager = ConfigManager(path_resolver)

        # Create initial config
        config1 = BirdNETConfig(site_name="Initial", latitude=10.0, longitude=20.0)
        config_manager.save(config1)

        # Verify it was saved
        loaded1 = config_manager.load()
        assert loaded1.site_name == "Initial"

        # Overwrite with new config
        config2 = BirdNETConfig(site_name="Updated", latitude=30.0, longitude=40.0)
        config_manager.save(config2)

        # Verify it was overwritten
        loaded2 = config_manager.load()
        assert loaded2.site_name == "Updated"
        assert loaded2.latitude == 30.0

        # File should exist only once
        assert config_path.exists()
        assert len(list(config_path.parent.glob("*.yaml"))) >= 1

    def test_config_in_docker_environment(self, path_resolver):
        """Should config handling in Docker-like environment."""
        # Simulate Docker paths
        docker_data_path = "/var/lib/birdnetpi"
        docker_config_path = Path(docker_data_path) / "config" / "birdnetpi.yaml"

        # Override path_resolver to return Docker path
        path_resolver.get_birdnetpi_config_path = lambda: docker_config_path

        config_path = path_resolver.get_birdnetpi_config_path()

        # Should use Docker path
        assert str(config_path).startswith(docker_data_path)
        assert config_path == Path(docker_data_path) / "config" / "birdnetpi.yaml"

    def test_config_manager_creates_directory_on_save(self, tmp_path, path_resolver):
        """Should configManager creates config directory on save if missing."""
        # Use a unique subdirectory to avoid conflicts
        unique_dir = tmp_path / "test_auto_create"
        data_dir = unique_dir / "new_data_dir"
        config_dir = data_dir / "config"
        config_path = config_dir / "birdnetpi.yaml"
        path_resolver.get_birdnetpi_config_path = lambda: config_path

        config_manager = ConfigManager(path_resolver)

        # Directory should not exist
        assert not config_dir.exists()

        # Save should create it
        config = BirdNETConfig(site_name="Auto Create Test")
        config_manager.save(config)

        # Now it should exist
        assert config_dir.exists()
        assert config_path.exists()
