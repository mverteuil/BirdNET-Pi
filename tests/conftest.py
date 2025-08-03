from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with a temporary base directory

    Still uses the legitimate templates and static files directories.
    """
    # Create a temporary directory for the repo root
    repo_root = tmp_path / "BirdNET-Pi"
    repo_root.mkdir()

    # Create a real FilePathResolver to get actual static and template paths
    real_resolver = FilePathResolver()

    # Create a MagicMock for FilePathResolver
    mock_resolver = MagicMock(spec=FilePathResolver)

    # Set base_dir to the temporary repo root
    mock_resolver.base_dir = str(repo_root)

    # Mock methods that should return paths within the temporary directory
    mock_resolver.get_birds_db_path.return_value = str(repo_root / "scripts" / "birds.db")
    mock_resolver.get_birdnetpi_config_path.return_value = str(
        repo_root / "config" / "birdnetpi.yaml"
    )
    mock_resolver.get_extracted_birdsounds_path.return_value = str(
        repo_root / "BirdSongs" / "Extracted" / "By_Date"
    )

    # Use the real methods for static and templates directories
    mock_resolver.get_static_dir.side_effect = real_resolver.get_static_dir
    mock_resolver.get_templates_dir.side_effect = real_resolver.get_templates_dir

    # Ensure the resolve method works with the mocked base_dir
    mock_resolver.resolve.side_effect = lambda *paths: str(
        Path(mock_resolver.base_dir).joinpath(*paths)
    )

    return mock_resolver


@pytest.fixture
def test_config_file(tmp_path: Path) -> Path:
    """Create a test configuration file with sensible defaults and temp paths."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "birdnetpi.yaml"

    # Create a config based on the actual config template with temp paths
    config_content = f"""
# BirdNET-Pi Test Configuration
# Basic Settings
site_name: Test BirdNET-Pi
latitude: 40.7128
longitude: -74.0060
model: BirdNET_GLOBAL_6K_V2.4_Model_FP16
sf_thresh: 0.03
confidence: 0.7
sensitivity: 1.25
week: 0
audio_format: mp3
extraction_length: 6.0
audio_device_index: -1
sample_rate: 48000
audio_channels: 1

# Data Storage Paths (using temp directory)
data:
  recordings_dir: {tmp_path}/recordings
  extracted_dir: {tmp_path}/extracted
  processed_dir: {tmp_path}/processed
  id_file: {tmp_path}/id.txt
  bird_db_file: {tmp_path}/BirdDB.txt
  db_path: {tmp_path}/birdnetpi.db

# Logging Configuration
logging:
  syslog_enabled: false
  syslog_host: localhost
  syslog_port: 514
  file_logging_enabled: false
  log_file_path: {tmp_path}/birdnetpi.log
  max_log_file_size_mb: 10
  log_file_backup_count: 5
  log_level: INFO

# External Service Integration
birdweather_id: ""

# Notification Settings
apprise_input: ""
apprise_notification_title: "BirdNET-Pi"
apprise_notification_body: "New bird detected"
apprise_notify_each_detection: false
apprise_notify_new_species: false
apprise_notify_new_species_each_day: false
apprise_weekly_report: false
minimum_time_limit: 0

# Flickr Integration
flickr_api_key: ""
flickr_filter_email: ""

# Localization
database_lang: en
timezone: UTC

# Web Interface Settings
caddy_pwd: ""
silence_update_indicator: false
birdnetpi_url: ""

# Species Filtering
apprise_only_notify_species_names: ""
apprise_only_notify_species_names_2: ""

# Field Mode and GPS Settings
enable_gps: false
gps_update_interval: 5.0

# Hardware Monitoring
hardware_check_interval: 10.0
enable_audio_device_check: false
enable_system_resource_check: true
enable_gps_check: false

# Analysis Configuration
sf_threshold: 0.03
privacy_threshold: 10.0
data_model_version: 2

# MQTT Integration Settings
enable_mqtt: false
mqtt_broker_host: localhost
mqtt_broker_port: 1883
mqtt_username: ""
mqtt_password: ""
mqtt_topic_prefix: birdnet
mqtt_client_id: birdnet-pi

# Webhook Integration Settings
enable_webhooks: true
webhook_urls: ""
webhook_events: detection,health,gps,system
"""
    config_file.write_text(config_content)

    # Create the data directories
    (tmp_path / "recordings").mkdir(exist_ok=True)
    (tmp_path / "extracted").mkdir(exist_ok=True)
    (tmp_path / "processed").mkdir(exist_ok=True)

    yield config_file

    # Cleanup is handled by pytest's tmp_path fixture


@pytest.fixture
def test_config(test_config_file: Path):
    """Load test configuration from the test config file."""
    from birdnetpi.utils.config_file_parser import ConfigFileParser

    parser = ConfigFileParser(str(test_config_file))
    return parser.load_config()


@pytest.fixture(scope="session", autouse=True)
def check_required_assets():
    """Check that required assets are available for testing."""
    from pathlib import Path

    from birdnetpi.utils.file_path_resolver import FilePathResolver

    file_resolver = FilePathResolver()
    missing_assets = []

    # Check for model files
    models_dir = Path(file_resolver.get_models_dir())
    if not models_dir.exists() or not any(models_dir.glob("*.tflite")):
        missing_assets.append("Model files (*.tflite)")

    # Check for labels.txt
    labels_path = Path(file_resolver.get_model_path("labels.txt"))
    if not labels_path.exists():
        missing_assets.append("labels.txt")

    # Check for IOC database
    db_path = Path(file_resolver.get_database_path())
    if not db_path.exists():
        missing_assets.append("IOC reference database")

    if missing_assets:
        print()
        print("┌" + "─" * 78 + "┐")
        print("│" + " " * 78 + "│")
        print("│  ⚠️  MISSING ASSETS FOR TESTING" + " " * 45 + "│")
        print("│" + " " * 78 + "│")
        print("│  The following required assets are missing for testing:" + " " * 22 + "│")
        for asset in missing_assets:
            spaces_needed = 76 - len(f"│    • {asset}")
            print(f"│    • {asset}" + " " * spaces_needed + "│")
        print("│" + " " * 78 + "│")
        print("│  To run tests with assets, install them first:" + " " * 29 + "│")
        print("│    export BIRDNETPI_DATA=./data" + " " * 43 + "│")
        print("│    uv run asset-installer install v2.1.0 --include-models --include-ioc-db│")
        print("│" + " " * 78 + "│")
        print("│  Most tests will still pass without assets (mocked dependencies)." + " " * 9 + "│")
        print(
            "│  Only integration tests and some service tests require real assets." + " " * 10 + "│"
        )
        print("│" + " " * 78 + "│")
        print("└" + "─" * 78 + "┘")
        print()
