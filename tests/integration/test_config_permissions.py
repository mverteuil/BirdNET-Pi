"""Tests for configuration file permissions and directory setup."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.system.path_resolver import PathResolver


class TestConfigPermissions:
    """Test configuration file and directory permissions."""

    def test_config_directory_creation(self):
        """Test that config directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set environment to use temp directory
            os.environ["BIRDNETPI_DATA"] = temp_dir

            try:
                path_resolver = PathResolver()
                config_path = path_resolver.get_birdnetpi_config_path()

                # Directory should not exist yet
                assert not config_path.parent.exists()

                # ConfigManager should create the directory
                config_manager = ConfigManager(path_resolver)
                config = BirdNETConfig(site_name="Test")
                config_manager.save(config)

                # Directory and file should now exist
                assert config_path.parent.exists()
                assert config_path.exists()

            finally:
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_config_write_permissions(self):
        """Test that config file can be written and read."""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["BIRDNETPI_DATA"] = temp_dir

            try:
                path_resolver = PathResolver()
                config_manager = ConfigManager(path_resolver)

                # Should be able to save
                config = BirdNETConfig(site_name="Permission Test", latitude=42.0, longitude=-71.0)

                # This should not raise any permission errors
                config_manager.save(config)

                # Should be able to read back
                loaded_config = config_manager.load()
                assert loaded_config.site_name == "Permission Test"
                assert loaded_config.latitude == 42.0

            finally:
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_config_handles_readonly_directory(self):
        """Test error handling when config directory is read-only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()

            # Make directory read-only (Unix only)
            if os.name != "nt":  # Not Windows
                os.chmod(config_dir, 0o444)

            os.environ["BIRDNETPI_DATA"] = temp_dir

            try:
                path_resolver = PathResolver()
                config_manager = ConfigManager(path_resolver)
                config = BirdNETConfig(site_name="Readonly Test")

                # Should handle permission error gracefully
                if os.name != "nt":  # Only test on Unix
                    with pytest.raises((PermissionError, OSError)):
                        config_manager.save(config)

            finally:
                # Restore write permissions for cleanup
                if os.name != "nt":
                    os.chmod(config_dir, 0o755)
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_config_creates_parent_directories(self):
        """Test that all parent directories are created as needed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use a deeply nested path
            nested_path = Path(temp_dir) / "deep" / "nested" / "path"
            os.environ["BIRDNETPI_DATA"] = str(nested_path)

            try:
                path_resolver = PathResolver()
                config_manager = ConfigManager(path_resolver)

                # Should create all parent directories
                config = BirdNETConfig(site_name="Nested Test")
                config_manager.save(config)

                # Verify all directories were created
                config_path = path_resolver.get_birdnetpi_config_path()
                assert config_path.exists()
                assert config_path.parent.exists()

            finally:
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_config_handles_existing_file(self):
        """Test that existing config files are properly overwritten."""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["BIRDNETPI_DATA"] = temp_dir

            try:
                path_resolver = PathResolver()
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
                config_path = path_resolver.get_birdnetpi_config_path()
                assert config_path.exists()
                assert len(list(config_path.parent.glob("*.yaml"))) >= 1

            finally:
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_config_in_docker_environment(self):
        """Test config handling in Docker-like environment."""
        # Simulate Docker paths
        docker_data_path = "/var/lib/birdnetpi"

        with patch.dict(os.environ, {"BIRDNETPI_DATA": docker_data_path}):
            path_resolver = PathResolver()
            config_path = path_resolver.get_birdnetpi_config_path()

            # Should use Docker path
            assert str(config_path).startswith(docker_data_path)
            assert config_path == Path(docker_data_path) / "config" / "birdnetpi.yaml"

    def test_config_manager_creates_directory_on_save(self):
        """Test that ConfigManager creates config directory on save if missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Point to a non-existent subdirectory
            data_dir = Path(temp_dir) / "new_data_dir"
            os.environ["BIRDNETPI_DATA"] = str(data_dir)

            try:
                path_resolver = PathResolver()
                config_manager = ConfigManager(path_resolver)

                # Directory should not exist
                config_dir = data_dir / "config"
                assert not config_dir.exists()

                # Save should create it
                config = BirdNETConfig(site_name="Auto Create Test")
                config_manager.save(config)

                # Now it should exist
                assert config_dir.exists()
                assert (config_dir / "birdnetpi.yaml").exists()

            finally:
                os.environ.pop("BIRDNETPI_DATA", None)
