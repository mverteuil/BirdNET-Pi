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
        "sf_thresh": 0.05,
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
        "database_lang": "fr",
        "timezone": "Europe/Paris",
        "caddy_pwd": "test_pwd",
        "silence_update_indicator": True,
        "birdnetpi_url": "test_url",
        "apprise_only_notify_species_names": "test_species",
        "apprise_only_notify_species_names_2": "test_species_2",
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
