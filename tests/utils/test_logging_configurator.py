import logging
from unittest.mock import MagicMock

import pytest

from birdnetpi.utils.logging_configurator import configure_logging


@pytest.fixture
def mock_config_parser():
    """Return a mock config parser."""
    mock = MagicMock()
    mock.logging = MagicMock()
    mock.logging.log_file_path = "/tmp/test_birdnetpi.log"
    mock.logging.log_level = "INFO"
    mock.logging.syslog_enabled = False
    mock.logging.file_logging_enabled = False
    mock.logging.syslog_host = "localhost"
    mock.logging.syslog_port = 514
    mock.logging.max_log_file_size_mb = 10
    mock.logging.log_file_backup_count = 5
    return mock


@pytest.fixture
def mock_config_parser_syslog_enabled():
    """Return a mock config parser with syslog enabled."""
    mock = MagicMock()
    mock.logging = MagicMock()
    mock.logging.log_file_path = "/tmp/test_birdnetpi.log"
    mock.logging.log_level = "INFO"
    mock.logging.syslog_enabled = True
    mock.logging.file_logging_enabled = False
    mock.logging.syslog_host = "localhost"
    mock.logging.syslog_port = 514
    mock.logging.max_log_file_size_mb = 10
    mock.logging.log_file_backup_count = 5
    return mock


@pytest.fixture
def mock_config_parser_file_logging_enabled():
    """Return a mock config parser with file logging enabled."""
    mock = MagicMock()
    mock.logging = MagicMock()
    mock.logging.log_file_path = "/tmp/test_birdnetpi.log"
    mock.logging.log_level = "INFO"
    mock.logging.syslog_enabled = False
    mock.logging.file_logging_enabled = True
    mock.logging.syslog_host = "localhost"
    mock.logging.syslog_port = 514
    mock.logging.max_log_file_size_mb = 10
    mock.logging.log_file_backup_count = 5
    return mock


class TestLoggingConfigurator:
    """Test the logging configurator."""

    def test_configure_logging_default(self, mock_config_parser):
        """Should configure logging with default settings."""
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)
        # We don't assert for FileHandler or SysLogHandler here as they are not enabled by default

    def test_configure_logging_debug_level(self, mock_config_parser):
        """Should configure logging with DEBUG level."""
        mock_config_parser.logging.log_level = "DEBUG"
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configure_logging_warning_level(self, mock_config_parser):
        """Should configure logging with WARNING level."""
        mock_config_parser.logging.log_level = "WARNING"
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_configure_logging_error_level(self, mock_config_parser):
        """Should configure logging with ERROR level."""
        mock_config_parser.logging.log_level = "ERROR"
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.ERROR

    def test_configure_logging_critical_level(self, mock_config_parser):
        """Should configure logging with CRITICAL level."""
        mock_config_parser.logging.log_level = "CRITICAL"
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.CRITICAL

    def test_configure_logging_invalid_level(self, mock_config_parser):
        """Should default to INFO level for invalid log level."""
        mock_config_parser.logging.log_level = "INVALID"
        configure_logging(mock_config_parser)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
