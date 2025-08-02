from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from birdnetpi.web.main import app


def test_read_main(file_path_resolver, tmp_path) -> None:
    """Test the main endpoint of the web application."""
    # Create a mock config object with all necessary attributes
    mock_config_instance = MagicMock()

    # Mock data attributes
    mock_config_instance.data = MagicMock()
    mock_config_instance.data.db_path = str(tmp_path / "test.db")

    mock_config_instance.site_name = "Test Site"

    # Mock audio attributes for SpectrogramService
    mock_config_instance.sample_rate = 48000
    mock_config_instance.channels = 1

    # Mock hardware monitoring attributes
    mock_config_instance.hardware_check_interval = 30.0
    mock_config_instance.enable_audio_device_check = True
    mock_config_instance.enable_system_resource_check = True
    mock_config_instance.enable_gps_check = False

    # Mock MQTT attributes
    mock_config_instance.enable_mqtt = False
    mock_config_instance.mqtt_broker_host = "localhost"
    mock_config_instance.mqtt_broker_port = 1883
    mock_config_instance.mqtt_username = ""
    mock_config_instance.mqtt_password = ""
    mock_config_instance.mqtt_topic_prefix = "birdnet"
    mock_config_instance.mqtt_client_id = "birdnet-pi"

    # Mock webhook attributes
    mock_config_instance.enable_webhooks = False
    mock_config_instance.webhook_urls = ""
    mock_config_instance.webhook_events = "detection,health,gps,system"

    # Mock GPS attributes
    mock_config_instance.enable_gps = False
    mock_config_instance.gps_update_interval = 10.0

    # Mock logging attributes
    mock_config_instance.logging = MagicMock()
    mock_config_instance.logging.syslog_enabled = False
    mock_config_instance.logging.syslog_host = "localhost"
    mock_config_instance.logging.syslog_port = 514
    mock_config_instance.logging.file_logging_enabled = False
    mock_config_instance.logging.log_file_path = str(tmp_path / "test.log")
    mock_config_instance.logging.max_log_file_size_mb = 10
    mock_config_instance.logging.log_file_backup_count = 5
    mock_config_instance.logging.log_level = "INFO"

    with patch("birdnetpi.web.main.ConfigFileParser") as mock_config_file_parser_class:
        mock_config_file_parser_class.return_value.load_config.return_value = mock_config_instance

        # Set app.state.file_resolver to the mocked file_path_resolver
        app.state.file_resolver = file_path_resolver

        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "BirdNET-Pi" in response.text
