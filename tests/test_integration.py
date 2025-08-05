from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from birdnetpi.managers.file_manager import FileManager
from birdnetpi.services.audio_fifo_reader_service import AudioFifoReaderService
from birdnetpi.web.core.factory import create_app


def test_read_main(file_path_resolver, tmp_path) -> None:
    """Test the main endpoint of the web application."""
    # Create a mock config object with all necessary attributes
    mock_config_instance = MagicMock()

    # Mock data attributes
    mock_config_instance.data = MagicMock()
    mock_config_instance.data.db_path = str(tmp_path / "test.db")

    mock_config_instance.site_name = "Test Site"
    mock_config_instance.latitude = 0.0
    mock_config_instance.longitude = 0.0

    # Mock audio attributes for SpectrogramService
    mock_config_instance.sample_rate = 48000
    mock_config_instance.audio_channels = 1

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
    mock_config_instance.logging.level = "INFO"
    mock_config_instance.logging.json_logs = False
    mock_config_instance.logging.include_caller = True
    mock_config_instance.logging.extra_fields = {}

    with patch(
        "birdnetpi.utils.config_file_parser.ConfigFileParser"
    ) as mock_config_file_parser_class:
        mock_config_file_parser_class.return_value.load_config.return_value = mock_config_instance

        # Mock FilePathResolver to use our fixture
        with patch(
            "birdnetpi.utils.file_path_resolver.FilePathResolver"
        ) as mock_file_resolver_class:
            mock_file_resolver_class.return_value = file_path_resolver

            # Mock structlog configurator to avoid git commands in tests
            with patch("birdnetpi.utils.structlog_configurator.configure_structlog"):
                # Mock FileManager to avoid directory permission issues
                with patch(
                    "birdnetpi.managers.file_manager.FileManager"
                ) as mock_file_manager_class:
                    mock_file_manager_instance = MagicMock(spec=FileManager)
                    mock_file_manager_class.return_value = mock_file_manager_instance

                    # Mock AudioFifoReaderService to avoid FIFO creation issues
                    with patch("birdnetpi.services.audio_fifo_reader_service.AudioFifoReaderService") as mock_fifo_class:
                        mock_fifo_instance = MagicMock(spec=AudioFifoReaderService)
                        mock_fifo_instance.start = AsyncMock()
                        mock_fifo_instance.stop = AsyncMock()
                        mock_fifo_class.return_value = mock_fifo_instance

                        app = create_app()
                        with TestClient(app) as client:
                            response = client.get("/")
                            assert response.status_code == 200
                            assert "BirdNET-Pi" in response.text
