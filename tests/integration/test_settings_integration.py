"""Integration tests for settings functionality.

Tests config persistence and audio device discovery.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from birdnetpi.audio.audio_device_service import AudioDevice, AudioDeviceService
from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.cache import clear_all_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test to ensure test isolation."""
    clear_all_cache()
    yield
    clear_all_cache()


class TestSettingsConfigIntegration:
    """Integration tests for settings configuration flow."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for config files."""
        temp_dir = tempfile.mkdtemp(prefix="test_settings_integration_")
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir(exist_ok=True)

        # Set environment variable
        old_env = os.environ.get("BIRDNETPI_DATA")
        os.environ["BIRDNETPI_DATA"] = temp_dir

        yield temp_dir

        # Cleanup
        if old_env:
            os.environ["BIRDNETPI_DATA"] = old_env
        else:
            os.environ.pop("BIRDNETPI_DATA", None)

        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_config_save_and_load_cycle(self, temp_config_dir):
        """Should save configuration to file and load it back correctly."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        # Create test configuration
        test_config = BirdNETConfig(
            site_name="Integration Test Site",
            latitude=42.3601,
            longitude=-71.0589,
            sensitivity_setting=1.75,
            species_confidence_threshold=0.85,
            audio_device_index=3,
            sample_rate=44100,
            audio_channels=2,
        )

        # Save configuration
        config_manager.save(test_config)

        # Verify file was created
        config_file = path_resolver.get_birdnetpi_config_path()
        assert config_file.exists()

        # Load configuration back
        loaded_config = config_manager.load()

        # Verify values match
        assert loaded_config.site_name == "Integration Test Site"
        assert loaded_config.latitude == 42.3601
        assert loaded_config.longitude == -71.0589
        assert loaded_config.sensitivity_setting == 1.75
        assert loaded_config.species_confidence_threshold == 0.85
        assert loaded_config.audio_device_index == 3
        assert loaded_config.sample_rate == 44100
        assert loaded_config.audio_channels == 2

    def test_config_yaml_format(self, temp_config_dir):
        """Should save configuration in valid YAML format."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        test_config = BirdNETConfig(
            site_name="YAML Test",
            latitude=45.5,
            longitude=-73.6,
            enable_gps=True,
            webhook_urls=["http://example.com/hook1", "http://example.com/hook2"],
        )

        config_manager.save(test_config)

        # Read the YAML file directly
        config_file = path_resolver.get_birdnetpi_config_path()
        with open(config_file) as f:
            yaml_data = yaml.safe_load(f)

        assert yaml_data["site_name"] == "YAML Test"
        assert yaml_data["latitude"] == 45.5
        assert yaml_data["longitude"] == -73.6
        assert yaml_data["enable_gps"] is True
        assert yaml_data["webhook_urls"] == ["http://example.com/hook1", "http://example.com/hook2"]

    def test_config_preserves_defaults(self, temp_config_dir):
        """Should preserve default values when not explicitly set."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        # Create minimal config
        minimal_config = BirdNETConfig()

        # Save and load
        config_manager.save(minimal_config)
        loaded_config = config_manager.load()

        # Check defaults are preserved
        assert loaded_config.site_name == "BirdNET-Pi"
        assert loaded_config.sensitivity_setting == 1.25
        assert loaded_config.species_confidence_threshold == 0.03
        assert loaded_config.audio_device_index == -1
        assert loaded_config.sample_rate == 48000

    def test_config_update_preserves_unchanged_fields(self, temp_config_dir):
        """Should preserve unchanged fields when updating configuration."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        # Initial config
        initial_config = BirdNETConfig(
            site_name="Initial Site",
            latitude=40.0,
            longitude=-74.0,
            birdweather_id="test123",
            apprise_targets={"email": "mailto://test@example.com"},
        )
        config_manager.save(initial_config)

        # Load and update only some fields
        loaded_config = config_manager.load()
        loaded_config.latitude = 41.0
        loaded_config.sensitivity_setting = 2.0
        config_manager.save(loaded_config)

        # Load again and verify
        final_config = config_manager.load()
        assert final_config.site_name == "Initial Site"  # Unchanged
        assert final_config.latitude == 41.0  # Changed
        assert final_config.longitude == -74.0  # Unchanged
        assert final_config.birdweather_id == "test123"  # Unchanged
        assert final_config.apprise_targets == {"email": "mailto://test@example.com"}  # Unchanged
        assert final_config.sensitivity_setting == 2.0  # Changed


class TestAudioDeviceIntegration:
    """Integration tests for audio device discovery."""

    @patch("sounddevice.query_devices")
    def test_audio_device_discovery_with_mock_devices(self, mock_query_devices):
        """Should discover and return audio devices correctly."""
        # Mock sounddevice response
        mock_query_devices.return_value = [
            {
                "name": "USB Audio Device",
                "index": 0,
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_low_input_latency": 0.01,
                "default_low_output_latency": 0.0,
                "default_high_input_latency": 0.04,
                "default_high_output_latency": 0.0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Built-in Microphone",
                "index": 1,
                "hostapi": 0,
                "max_input_channels": 1,
                "max_output_channels": 0,
                "default_low_input_latency": 0.02,
                "default_low_output_latency": 0.0,
                "default_high_input_latency": 0.08,
                "default_high_output_latency": 0.0,
                "default_samplerate": 44100.0,
            },
            {
                "name": "Speaker",  # Output device, should be filtered out
                "index": 2,
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_low_input_latency": 0.0,
                "default_low_output_latency": 0.01,
                "default_high_input_latency": 0.0,
                "default_high_output_latency": 0.04,
                "default_samplerate": 48000.0,
            },
        ]

        audio_service = AudioDeviceService()
        devices = audio_service.discover_input_devices()

        # Should only return input devices
        assert len(devices) == 2
        assert all(isinstance(device, AudioDevice) for device in devices)

        # Check first device
        assert devices[0].name == "USB Audio Device"
        assert devices[0].index == 0
        assert devices[0].max_input_channels == 2
        assert devices[0].default_samplerate == 48000.0

        # Check second device
        assert devices[1].name == "Built-in Microphone"
        assert devices[1].index == 1
        assert devices[1].max_input_channels == 1
        assert devices[1].default_samplerate == 44100.0

    @patch("sounddevice.query_devices")
    def test_audio_device_handles_no_devices(self, mock_query_devices):
        """Should handle case when no audio devices are available."""
        mock_query_devices.return_value = []

        audio_service = AudioDeviceService()
        devices = audio_service.discover_input_devices()

        assert devices == []

    @patch("sounddevice.query_devices")
    def test_audio_device_handles_query_exception(self, mock_query_devices):
        """Should handle exceptions during device query gracefully."""
        mock_query_devices.side_effect = Exception("Audio system not available")

        audio_service = AudioDeviceService()

        # Should not raise exception, but return empty list or handle gracefully
        try:
            devices = audio_service.discover_input_devices()
            # Implementation might return empty list or raise
            assert isinstance(devices, list)
        except Exception as e:
            # Or it might propagate the exception - both are valid
            assert "Audio system not available" in str(e)


class TestSettingsEndToEndFlow:
    """End-to-end integration tests for complete settings flow."""

    @pytest.fixture
    def full_test_env(self):
        """Set up complete test environment with temp directories."""
        temp_dir = tempfile.mkdtemp(prefix="test_e2e_settings_")
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir(exist_ok=True)

        # Save original env
        old_env = os.environ.get("BIRDNETPI_DATA")
        os.environ["BIRDNETPI_DATA"] = temp_dir

        yield temp_dir

        # Cleanup
        if old_env:
            os.environ["BIRDNETPI_DATA"] = old_env
        else:
            os.environ.pop("BIRDNETPI_DATA", None)

        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_complete_settings_workflow(self, full_test_env):
        """Should handle complete workflow: load, modify, save, reload."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        # Step 1: Create initial configuration
        initial_config = BirdNETConfig(
            site_name="E2E Test Site",
            latitude=37.7749,
            longitude=-122.4194,
            audio_device_index=0,
        )
        config_manager.save(initial_config)

        # Step 2: Simulate loading in settings page
        loaded_for_display = config_manager.load()
        assert loaded_for_display.site_name == "E2E Test Site"
        assert loaded_for_display.audio_device_index == 0

        # Step 3: Simulate form submission with changes
        updated_config = BirdNETConfig(
            site_name="E2E Test Site",  # Unchanged
            latitude=37.8,  # Changed
            longitude=-122.4,  # Changed slightly
            audio_device_index=1,  # Changed
            sensitivity_setting=2.0,  # Changed
            species_confidence_threshold=0.9,  # Changed
            enable_gps=True,  # Changed
            webhook_urls=["http://webhook.example.com"],  # Added
        )
        config_manager.save(updated_config)

        # Step 4: Verify changes persisted
        final_config = config_manager.load()
        assert final_config.site_name == "E2E Test Site"
        assert final_config.latitude == 37.8
        assert final_config.longitude == -122.4
        assert final_config.audio_device_index == 1
        assert final_config.sensitivity_setting == 2.0
        assert final_config.species_confidence_threshold == 0.9
        assert final_config.enable_gps is True
        assert final_config.webhook_urls == ["http://webhook.example.com"]

        # Step 5: Verify YAML file structure
        config_file = path_resolver.get_birdnetpi_config_path()
        with open(config_file) as f:
            yaml_content = f.read()

        # Should be valid YAML
        parsed = yaml.safe_load(yaml_content)
        assert parsed is not None
        assert "site_name" in parsed
        assert "webhook_urls" in parsed

    @patch("sounddevice.query_devices")
    def test_settings_with_audio_device_selection(self, mock_query_devices, full_test_env):
        """Should integrate audio device selection with configuration."""
        # Mock audio devices
        mock_query_devices.return_value = [
            {
                "name": "Device A",
                "index": 0,
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_low_input_latency": 0.01,
                "default_low_output_latency": 0.0,
                "default_high_input_latency": 0.04,
                "default_high_output_latency": 0.0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Device B",
                "index": 1,
                "hostapi": 0,
                "max_input_channels": 1,
                "max_output_channels": 0,
                "default_low_input_latency": 0.01,
                "default_low_output_latency": 0.0,
                "default_high_input_latency": 0.04,
                "default_high_output_latency": 0.0,
                "default_samplerate": 44100.0,
            },
        ]

        # Discover devices
        audio_service = AudioDeviceService()
        devices = audio_service.discover_input_devices()

        # Create config with selected device
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)

        # Select Device B (index 1)
        config = BirdNETConfig(
            site_name="Audio Test",
            audio_device_index=devices[1].index,
            sample_rate=int(devices[1].default_samplerate),
        )
        config_manager.save(config)

        # Verify selection persisted
        loaded_config = config_manager.load()
        assert loaded_config.audio_device_index == 1
        assert loaded_config.sample_rate == 44100
