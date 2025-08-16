"""Comprehensive tests for ConfigFileParser covering all major functionality."""

import pytest
import yaml

from birdnetpi.utils.config_file_parser import ConfigFileParser


@pytest.fixture
def config_file(tmp_path):
    """Fixture that creates a temporary YAML config file for testing."""
    config_data = {
        "site_name": "Test Site",
        "latitude": 12.34,
        "longitude": 56.78,
        "model": "Test_Model",
        "species_confidence_threshold": 0.05,
        "confidence": 0.75,
        "sensitivity": 1.5,
        "week": 1,
        "audio_format": "wav",
        "extraction_length": 5.0,
        "birdweather_id": "test_id",
        "apprise_input": "test_input",
        "apprise_notification_title": "Test Title",
        "apprise_notification_body": "Test Body",
        "apprise_notify_each_detection": True,
        "apprise_notify_new_species": True,
        "apprise_notify_new_species_each_day": True,
        "apprise_weekly_report": True,
        "minimum_time_limit": 1,
        "flickr_api_key": "test_key",
        "flickr_filter_email": "test_email",
        "language": "fr",
        "timezone": "Europe/Paris",
        "apprise_only_notify_species_names": "test_species",
    }
    path = tmp_path / "test_config.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(config_data, f)
    return path


def test_load_config(config_file):
    """Should correctly load a YAML config file."""
    parser = ConfigFileParser(config_file)
    config = parser.load_config()
    assert config.site_name == "Test Site"
    assert config.latitude == 12.34
    assert config.longitude == 56.78


def test_save_config(config_file):
    """Should correctly save a BirdNETConfig object to a YAML file."""
    parser = ConfigFileParser(config_file)
    config = parser.load_config()
    config.site_name = "New Test Site"
    parser.save_config(config)
    with open(config_file) as f:
        new_config_data = yaml.safe_load(f)
    assert new_config_data["site_name"] == "New Test Site"


class TestConfigFileParserInitialization:
    """Test ConfigFileParser initialization with different path configurations."""

    def test_init___no_config_path_uses_path_resolver(self, mocker, tmp_path, path_resolver):
        """Should use PathResolver when no config_path provided."""
        # Create actual paths in tmp_path to avoid MagicMock file creation
        config_path = tmp_path / "config.yaml"
        template_path = tmp_path / "template.yaml"

        # Customize the global path_resolver
        path_resolver.get_birdnetpi_config_path = lambda: config_path
        path_resolver.get_config_template_path = lambda: template_path

        mock_resolver = mocker.patch(
            "birdnetpi.utils.config_file_parser.PathResolver", return_value=path_resolver
        )

        parser = ConfigFileParser()

        assert parser.config_path == str(config_path)
        assert parser.template_path == str(template_path)
        mock_resolver.assert_called_once()

    def test_init__explicit_config_path(self):
        """Should use explicit path when provided and derive template path."""
        config_path = "/custom/path/config.yaml"

        parser = ConfigFileParser(config_path)

        assert parser.config_path == config_path
        assert parser.template_path == "/custom/config_templates/birdnetpi.yaml"

    def test_init__nested_config_path(self):
        """Should correctly derive template path from nested config path."""
        config_path = "/app/data/config/birdnetpi.yaml"

        parser = ConfigFileParser(config_path)

        assert parser.config_path == config_path
        assert parser.template_path == "/app/data/config_templates/birdnetpi.yaml"


class TestConfigFileParserAdvancedLoading:
    """Test advanced configuration file loading scenarios."""

    def test_load_config__full_config_including_new_fields(self, tmp_path):
        """Should load configuration with all new fields including GPS, MQTT, webhooks."""
        config_file = tmp_path / "full_config.yaml"
        config_data = {
            "site_name": "Full Test Site",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite",
            "confidence": 0.8,
            "sensitivity": 1.5,
            "week": 48,
            "audio_format": "wav",
            "birdweather_id": "test-id",
            "enable_gps": True,
            "gps_update_interval": 15.0,
            "hardware_check_interval": 30.0,
            "enable_audio_device_check": False,
            "enable_system_resource_check": False,
            "enable_gps_check": True,
            "privacy_threshold": 20.0,
            "enable_mqtt": True,
            "mqtt_broker_host": "test-broker",
            "mqtt_broker_port": 1883,
            "mqtt_username": "test-user",
            "mqtt_password": "test-pass",
            "mqtt_topic_prefix": "test-birdnet",
            "mqtt_client_id": "test-client",
            "enable_webhooks": True,
            "webhook_urls": ["https://example.com/webhook1", "https://example.com/webhook2"],
            "audio_device_index": 2,
            "sample_rate": 44100,
            "audio_channels": 2,
            "logging": {
                "level": "DEBUG",
                "json_logs": True,
                "include_caller": True,
                "extra_fields": {"service": "test-service", "env": "test"},
            },
        }

        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        parser = ConfigFileParser(str(config_file))
        config = parser.load_config()

        # Test new GPS fields
        assert config.enable_gps is True
        assert config.gps_update_interval == 15.0
        assert config.hardware_check_interval == 30.0
        assert config.enable_audio_device_check is False
        assert config.enable_system_resource_check is False
        assert config.enable_gps_check is True
        assert config.privacy_threshold == 20.0

        # Test MQTT config
        assert config.enable_mqtt is True
        assert config.mqtt_broker_host == "test-broker"
        assert config.mqtt_broker_port == 1883
        assert config.mqtt_username == "test-user"
        assert config.mqtt_password == "test-pass"
        assert config.mqtt_topic_prefix == "test-birdnet"
        assert config.mqtt_client_id == "test-client"

        # Test webhook config
        assert config.enable_webhooks is True
        assert config.webhook_urls == [
            "https://example.com/webhook1",
            "https://example.com/webhook2",
        ]

        # Test audio device config
        assert config.audio_device_index == 2
        assert config.sample_rate == 44100
        assert config.audio_channels == 2

        # Test logging config
        assert config.logging.level == "DEBUG"
        assert config.logging.json_logs is True
        assert config.logging.include_caller is True
        assert config.logging.extra_fields == {"service": "test-service", "env": "test"}

    def test_load_config__legacy_sf_thresh(self, tmp_path):
        """Should handle legacy sf_thresh field for species_confidence_threshold."""
        config_file = tmp_path / "legacy_config.yaml"
        config_data = {
            "site_name": "Legacy Site",
            "sf_thresh": 0.05,  # Legacy field name
        }

        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        parser = ConfigFileParser(str(config_file))
        config = parser.load_config()

        assert config.species_confidence_threshold == 0.05

    def test_load_config_creates_from_template__missing(self, tmp_path):
        """Should create config from template if config file doesn't exist."""
        template_file = tmp_path / "template.yaml"
        config_file = tmp_path / "config.yaml"

        template_data = {
            "site_name": "Template Site",
            "latitude": 1.0,
            "longitude": 2.0,
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite",
        }

        with open(template_file, "w") as f:
            yaml.safe_dump(template_data, f)

        # Mock template path to point to our test template
        parser = ConfigFileParser(str(config_file))
        parser.template_path = str(template_file)

        config = parser.load_config()

        # Config file should now exist and contain template data
        assert config_file.exists()
        assert config.site_name == "Template Site"
        assert config.latitude == 1.0
        assert config.longitude == 2.0

    def test_load_config_creates_minimal___no_template(self, tmp_path):
        """Should create minimal config if both config and template are missing."""
        config_file = tmp_path / "config.yaml"
        template_file = tmp_path / "nonexistent_template.yaml"

        parser = ConfigFileParser(str(config_file))
        parser.template_path = str(template_file)

        config = parser.load_config()

        # Config file should be created with minimal defaults
        assert config_file.exists()
        assert config.site_name == "BirdNET-Pi"
        assert config.latitude == 0.0
        assert config.longitude == 0.0
        assert config.model == "BirdNET_GLOBAL_6K_V2.4_Model_FP16"
        assert config.species_confidence_threshold == 0.03
        assert config.sensitivity_setting == 1.25


class TestWebhookUrlParsing:
    """Test webhook URL parsing functionality."""

    def test_parse_webhook_urls__string_format(self):
        """Should parse comma-separated string format webhook URLs."""
        parser = ConfigFileParser("/dummy/path")

        urls_string = "https://example.com/webhook1, https://example.com/webhook2 ,https://example.com/webhook3"
        result = parser._parse_webhook_urls(urls_string)

        expected = [
            "https://example.com/webhook1",
            "https://example.com/webhook2",
            "https://example.com/webhook3",
        ]
        assert result == expected

    def test_parse_webhook_urls__list_format(self):
        """Should parse list format webhook URLs."""
        parser = ConfigFileParser("/dummy/path")

        urls_list = ["https://example.com/webhook1", "https://example.com/webhook2"]
        result = parser._parse_webhook_urls(urls_list)

        assert result == urls_list

    def test_parse_webhook_urls___empty_string(self):
        """Should handle empty string webhook URLs."""
        parser = ConfigFileParser("/dummy/path")

        result = parser._parse_webhook_urls("")

        assert result == []

    def test_parse_webhook_urls__none_input(self):
        """Should handle None input for webhook URLs."""
        parser = ConfigFileParser("/dummy/path")

        result = parser._parse_webhook_urls(None)

        assert result == []


class TestLoggingConfigParsing:
    """Test logging configuration parsing functionality."""

    def test_parse_logging_config__full_config(self):
        """Should parse complete logging configuration."""
        parser = ConfigFileParser("/dummy/path")

        logging_section = {
            "level": "DEBUG",
            "json_logs": True,
            "include_caller": True,
            "extra_fields": {"service": "test-service", "env": "test"},
        }

        result = parser._parse_logging_config(logging_section)

        assert result.level == "DEBUG"
        assert result.json_logs is True
        assert result.include_caller is True
        assert result.extra_fields == {"service": "test-service", "env": "test"}

    def test_parse_logging_config__minimal_config(self):
        """Should parse minimal logging configuration with defaults."""
        parser = ConfigFileParser("/dummy/path")

        logging_section = {}

        result = parser._parse_logging_config(logging_section)

        assert result.level == "INFO"
        assert result.json_logs is None
        assert result.include_caller is False
        assert result.extra_fields == {"service": "birdnet-pi"}


class TestConfigFileEnsureExists:
    """Test configuration file existence ensuring functionality."""

    def test_ensure_config_exists_does_nothing__file_exists(self, tmp_path):
        """Should not modify existing config file."""
        config_file = tmp_path / "config.yaml"
        original_content = {"site_name": "Existing Site"}

        with open(config_file, "w") as f:
            yaml.safe_dump(original_content, f)

        parser = ConfigFileParser(str(config_file))
        parser._ensure_config_exists()

        # File should still exist with original content
        assert config_file.exists()
        with open(config_file) as f:
            content = yaml.safe_load(f)
        assert content == original_content

    def test_ensure_config_exists_copies_from_template(self, tmp_path):
        """Should copy from template when config doesn't exist."""
        config_file = tmp_path / "config.yaml"
        template_file = tmp_path / "template.yaml"

        template_content = {"site_name": "Template Site", "latitude": 1.0}
        with open(template_file, "w") as f:
            yaml.safe_dump(template_content, f)

        parser = ConfigFileParser(str(config_file))
        parser.template_path = str(template_file)
        parser._ensure_config_exists()

        # Config should now exist with template content
        assert config_file.exists()
        with open(config_file) as f:
            content = yaml.safe_load(f)
        assert content == template_content

    def test_ensure_config_exists_creates_minimal_config_without_template(self, tmp_path):
        """Should create minimal config when template doesn't exist."""
        config_file = tmp_path / "config.yaml"
        template_file = tmp_path / "nonexistent_template.yaml"

        parser = ConfigFileParser(str(config_file))
        parser.template_path = str(template_file)
        parser._ensure_config_exists()

        # Config should be created with minimal content
        assert config_file.exists()
        with open(config_file) as f:
            content = yaml.safe_load(f)

        expected_minimal = {
            "site_name": "BirdNET-Pi",
            "latitude": 0.0,
            "longitude": 0.0,
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "species_confidence_threshold": 0.03,
            "sensitivity_setting": 1.25,
        }
        assert content == expected_minimal
