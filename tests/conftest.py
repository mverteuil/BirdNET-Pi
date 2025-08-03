from pathlib import Path

import matplotlib
import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with test database isolation.

    Uses the repo's ./data directory for models and assets (set by session fixture),
    but temp directories for test databases to avoid conflicts.
    """
    # Create a real FilePathResolver (environment is already set by session fixture)
    resolver = FilePathResolver()

    # Override database path to use temp directory for test isolation
    def get_test_database_path():
        # Create temp database directory
        test_db_dir = tmp_path / "database"
        test_db_dir.mkdir(exist_ok=True)
        return str(test_db_dir / "birdnetpi.db")

    resolver.get_database_path = get_test_database_path
    resolver.get_database_dir = lambda: str(tmp_path / "database")

    return resolver


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
species_confidence_threshold: 0.03
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
species_confidence_threshold: 0.03
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
def setup_test_environment():
    """Set up test environment with proper paths to repo data directory."""
    import os
    from pathlib import Path

    # Get project root directory
    project_root = Path(__file__).parent.parent

    # Store original environment variables
    original_app_env = os.environ.get("BIRDNETPI_APP")
    original_data_env = os.environ.get("BIRDNETPI_DATA")

    # Set environment variables to point to real repo directories for the entire test session
    os.environ["BIRDNETPI_APP"] = str(project_root)
    os.environ["BIRDNETPI_DATA"] = str(project_root / "data")

    yield

    # Restore original environment variables
    if original_app_env is not None:
        os.environ["BIRDNETPI_APP"] = original_app_env
    else:
        os.environ.pop("BIRDNETPI_APP", None)

    if original_data_env is not None:
        os.environ["BIRDNETPI_DATA"] = original_data_env
    else:
        os.environ.pop("BIRDNETPI_DATA", None)


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

    # Note: labels.txt is legacy - IOC database is now used for bird species names

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
