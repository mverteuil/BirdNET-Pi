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

    with (
        patch("birdnetpi.web.main.ConfigFileParser") as mock_config_file_parser_class,
        patch("birdnetpi.web.main.FilePathResolver") as mock_file_path_resolver_class,
    ):
        # Configure the mock ConfigFileParser to return the mock config instance
        mock_config_file_parser_instance = mock_config_file_parser_class.return_value
        mock_config_file_parser_instance.load_config.return_value = mock_config_instance

        # Configure the mock FilePathResolver to return valid paths within tmp_path
        mock_file_path_resolver_instance = mock_file_path_resolver_class.return_value
        mock_file_path_resolver_instance.get_static_dir.return_value = str(
            tmp_path / "static"
        )

        # Create the mocked directories
        (tmp_path / "static").mkdir()

        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "BirdNET-Pi" in response.text
