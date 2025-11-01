"""Tests for system setup CLI."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from gpsdclient.client import GPSDClient

from birdnetpi.cli.setup_system import (
    configure_audio_device,
    configure_device_name,
    configure_gps,
    configure_language,
    configure_location,
    detect_audio_devices,
    detect_gps,
    get_boot_config,
    get_common_timezones,
    get_supported_languages,
    is_attended_install,
    main,
)
from birdnetpi.config.models import BirdNETConfig


class TestDetectAudioDevices:
    """Tests for audio device detection."""

    def test_detect_usb_device_preferred(self):
        """Should prefer USB devices over built-in devices."""
        mock_devices = [
            {
                "name": "Built-in Microphone",
                "default_samplerate": 44100,
                "max_input_channels": 1,
            },
            {
                "name": "USB Audio Device",
                "default_samplerate": 48000,
                "max_input_channels": 2,
            },
        ]

        with patch("sounddevice.query_devices", return_value=mock_devices):
            device_idx, device_name = detect_audio_devices()

        assert device_idx == 1
        assert device_name == "USB Audio Device"

    def test_detect_best_sample_rate_among_usb(self):
        """Should select highest sample rate among USB devices."""
        mock_devices = [
            {
                "name": "USB Microphone 48kHz",
                "default_samplerate": 48000,
                "max_input_channels": 1,
            },
            {
                "name": "USB Microphone 96kHz",
                "default_samplerate": 96000,
                "max_input_channels": 1,
            },
        ]

        with patch("sounddevice.query_devices", return_value=mock_devices):
            device_idx, device_name = detect_audio_devices()

        assert device_idx == 1
        assert device_name == "USB Microphone 96kHz"

    def test_fallback_to_non_usb(self):
        """Should fallback to non-USB device when no USB available."""
        mock_devices = [
            {
                "name": "Built-in Microphone",
                "default_samplerate": 44100,
                "max_input_channels": 1,
            },
        ]

        with patch("sounddevice.query_devices", return_value=mock_devices):
            device_idx, device_name = detect_audio_devices()

        assert device_idx == 0
        assert device_name == "Built-in Microphone"

    def test_skip_output_only_devices(self):
        """Should skip output-only devices."""
        mock_devices = [
            {
                "name": "Speakers",
                "default_samplerate": 44100,
                "max_input_channels": 0,  # No input
            },
            {
                "name": "Microphone",
                "default_samplerate": 48000,
                "max_input_channels": 1,
            },
        ]

        with patch("sounddevice.query_devices", return_value=mock_devices):
            device_idx, device_name = detect_audio_devices()

        assert device_idx == 1
        assert device_name == "Microphone"

    def test_no_input_devices_found(self):
        """Should handle when no input devices are found."""
        mock_devices = [
            {
                "name": "Speakers",
                "default_samplerate": 44100,
                "max_input_channels": 0,
            },
        ]

        with patch("sounddevice.query_devices", return_value=mock_devices):
            device_idx, device_name = detect_audio_devices()

        assert device_idx is None
        assert device_name == "No input devices found"


class TestDetectGPS:
    """Tests for GPS detection."""

    def test_gps_detection_success(self):
        """Should detect GPS location when fix is available."""
        mock_packet = {"mode": 3, "lat": 40.7128, "lon": -74.0060}

        mock_client = MagicMock(spec=GPSDClient)
        mock_client.dict_stream.return_value = [mock_packet]

        with patch("birdnetpi.cli.setup_system.GPSDClient", return_value=mock_client):
            with patch("birdnetpi.cli.setup_system.get_localzone", return_value="America/New_York"):
                lat, lon, tz = detect_gps()

        assert lat == 40.7128
        assert lon == -74.0060
        assert tz == "America/New_York"

    def test_gps_detection_no_fix(self):
        """Should return None when GPS has no fix."""
        mock_packet = {"mode": 1}  # No fix

        mock_client = MagicMock(spec=GPSDClient)
        mock_client.dict_stream.return_value = [mock_packet]

        with patch("birdnetpi.cli.setup_system.GPSDClient", return_value=mock_client):
            lat, lon, tz = detect_gps()

        assert lat is None
        assert lon is None
        assert tz is None

    def test_gps_detection_exception(self):
        """Should handle when gpsd is not available."""
        with patch(
            "birdnetpi.cli.setup_system.GPSDClient", side_effect=Exception("gpsd not running")
        ):
            lat, lon, tz = detect_gps()

        assert lat is None
        assert lon is None
        assert tz is None


class TestGetBootConfig:
    """Tests for boot configuration loading."""

    def test_get_boot_config_exists(self, tmp_path):
        """Should load boot configuration when file exists."""
        boot_config = tmp_path / "birdnetpi_config.txt"
        boot_config.write_text(
            """# BirdNET-Pi boot configuration
device_name=My BirdNET Device
latitude=40.7128
longitude=-74.0060
language=en
"""
        )

        with patch("birdnetpi.cli.setup_system.Path", return_value=boot_config):
            config = get_boot_config()

        assert config["device_name"] == "My BirdNET Device"
        assert config["latitude"] == "40.7128"
        assert config["longitude"] == "-74.0060"
        assert config["language"] == "en"

    def test_get_boot_config_not_exists(self):
        """Should return empty dict when boot configuration doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            config = get_boot_config()

        assert config == {}

    def test_get_boot_config_skip_comments(self, tmp_path):
        """Should skip comments and empty lines."""
        boot_config = tmp_path / "birdnetpi_config.txt"
        boot_config.write_text(
            """# This is a comment

device_name=Test Device
# Another comment
language=es
"""
        )

        with patch("birdnetpi.cli.setup_system.Path", return_value=boot_config):
            config = get_boot_config()

        assert len(config) == 2
        assert config["device_name"] == "Test Device"
        assert config["language"] == "es"


class TestIsAttendedInstall:
    """Tests for attended install detection."""

    def test_attended_install_tty(self):
        """Should detect attended install when stdin is a TTY."""
        with patch("sys.stdin.isatty", return_value=True):
            assert is_attended_install() is True

    def test_unattended_install_no_tty(self):
        """Should detect unattended install when stdin is not a TTY."""
        with patch("sys.stdin.isatty", return_value=False):
            assert is_attended_install() is False


class TestGetCommonTimezones:
    """Tests for timezone list."""

    def test_get_common_timezones(self):
        """Should return common timezones."""
        timezones = get_common_timezones()

        assert isinstance(timezones, list)
        assert "America/New_York" in timezones
        assert "Europe/London" in timezones
        assert "Asia/Tokyo" in timezones


class TestGetSupportedLanguages:
    """Tests for language support detection."""

    def test_get_supported_languages_from_database(self, path_resolver, tmp_path):
        """Should get languages from IOC database."""
        # Create a temporary database
        db_path = tmp_path / "ioc_reference.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE languages (
                language_code VARCHAR(10) PRIMARY KEY,
                language_name VARCHAR(50),
                language_family VARCHAR(30),
                translation_count INTEGER
            )
            """
        )
        cursor.execute("INSERT INTO languages VALUES ('en', 'English', NULL, 10983)")
        cursor.execute("INSERT INTO languages VALUES ('es', 'Spanish', NULL, 10823)")
        cursor.execute("INSERT INTO languages VALUES ('fr', 'French', NULL, 10983)")
        conn.commit()
        conn.close()

        # Override path_resolver to return our test database
        path_resolver.get_ioc_database_path = lambda: db_path

        languages = get_supported_languages(path_resolver)

        assert "en" in languages
        assert languages["en"] == ("English", 10983)
        assert "es" in languages
        assert languages["es"] == ("Spanish", 10823)

    def test_get_supported_languages_fallback(self, path_resolver):
        """Should fallback when database not available."""
        # Override to return non-existent path
        path_resolver.get_ioc_database_path = lambda: Path("/nonexistent/db.db")

        languages = get_supported_languages(path_resolver)

        assert "en" in languages
        assert isinstance(languages["en"], tuple)
        assert len(languages["en"]) == 2


class TestConfigureAudioDevice:
    """Tests for audio device configuration."""

    def test_configure_audio_device_found(self):
        """Should configure audio device when device is found."""
        config = BirdNETConfig()

        with patch(
            "birdnetpi.cli.setup_system.detect_audio_devices", return_value=(2, "USB Microphone")
        ):
            configure_audio_device(config)

        assert config.audio_device_index == 2

    def test_configure_audio_device_not_found(self):
        """Should leave default when no device is found."""
        config = BirdNETConfig()

        with patch(
            "birdnetpi.cli.setup_system.detect_audio_devices",
            return_value=(None, "No input devices found"),
        ):
            configure_audio_device(config)

        # Should remain at default value
        assert config.audio_device_index == -1


class TestConfigureGPS:
    """Tests for GPS configuration."""

    def test_configure_gps_success(self):
        """Should configure GPS when GPS is detected."""
        config = BirdNETConfig()

        with patch(
            "birdnetpi.cli.setup_system.detect_gps",
            return_value=(40.7128, -74.0060, "America/New_York"),
        ):
            lat, lon = configure_gps(config)

        assert config.latitude == 40.7128
        assert config.longitude == -74.0060
        assert config.timezone == "America/New_York"
        assert lat == 40.7128
        assert lon == -74.0060

    def test_configure_gps_not_detected(self):
        """Should leave defaults when GPS is not detected."""
        config = BirdNETConfig()
        original_lat = config.latitude
        original_lon = config.longitude

        with patch("birdnetpi.cli.setup_system.detect_gps", return_value=(None, None, None)):
            lat, lon = configure_gps(config)

        assert config.latitude == original_lat
        assert config.longitude == original_lon
        assert lat is None
        assert lon is None


class TestBootConfigIntegration:
    """Tests for boot config integration in configure functions."""

    def test_configure_device_name_from_boot_config(self):
        """Should use device name from boot config."""
        config = BirdNETConfig()
        boot_config = {"device_name": "My Custom Device"}

        configure_device_name(config, boot_config)

        assert config.site_name == "My Custom Device"

    def test_configure_device_name_prompt_when_not_in_boot_config(self):
        """Should prompt for device name when not in boot config."""
        config = BirdNETConfig()
        boot_config = {}

        with patch("click.prompt", return_value="Prompted Device"):
            configure_device_name(config, boot_config)

        assert config.site_name == "Prompted Device"

    def test_configure_location_from_boot_config(self):
        """Should use location from boot config."""
        config = BirdNETConfig()
        boot_config = {
            "latitude": "51.5074",
            "longitude": "-0.1278",
            "timezone": "Europe/London",
        }

        configure_location(config, boot_config, lat_detected=None)

        assert config.latitude == 51.5074
        assert config.longitude == -0.1278
        assert config.timezone == "Europe/London"

    def test_configure_location_skip_when_gps_detected(self):
        """Should skip prompts when GPS already detected location."""
        config = BirdNETConfig()
        config.latitude = 40.7128
        config.longitude = -74.0060
        boot_config = {}

        # When GPS detected (lat_detected is not None), should not prompt
        configure_location(config, boot_config, lat_detected=40.7128)

        # Config values should remain from GPS detection
        assert config.latitude == 40.7128
        assert config.longitude == -74.0060

    def test_configure_location_boot_config_overrides_defaults(self):
        """Should use boot config location even when defaults exist."""
        config = BirdNETConfig()
        # Config has some default values
        config.latitude = 0.0
        config.longitude = 0.0

        boot_config = {
            "latitude": "48.8566",
            "longitude": "2.3522",
            "timezone": "Europe/Paris",
        }

        configure_location(config, boot_config, lat_detected=None)

        assert config.latitude == 48.8566
        assert config.longitude == 2.3522
        assert config.timezone == "Europe/Paris"

    def test_configure_language_from_boot_config(self, path_resolver):
        """Should use language from boot config."""
        config = BirdNETConfig()
        boot_config = {"language": "es"}

        configure_language(config, boot_config, path_resolver)

        assert config.language == "es"

    def test_configure_language_prompt_when_not_in_boot_config(self, path_resolver):
        """Should prompt for language when not in boot config."""
        config = BirdNETConfig()
        boot_config = {}

        # Mock the database to avoid filesystem dependencies
        path_resolver.get_ioc_database_path = lambda: Path("/nonexistent/db.db")

        with patch("click.prompt", return_value="fr"):
            configure_language(config, boot_config, path_resolver)

        assert config.language == "fr"


class TestMainCLI:
    """Integration tests for main CLI."""

    def test_main_config_already_exists(self, path_resolver):
        """Should skip setup when config already exists."""
        runner = CliRunner()

        # Make config appear to exist
        path_resolver.get_birdnetpi_config_path = lambda: Path(__file__)

        with patch("birdnetpi.cli.setup_system.PathResolver", return_value=path_resolver):
            result = runner.invoke(main)

        assert result.exit_code == 0
        assert "Configuration already exists" in result.output
