from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.log_reader import LogReaderService


@pytest.fixture
def log_service():
    """Provide a LogReaderService instance for testing."""
    return LogReaderService()


@patch("birdnetpi.system.log_reader.subprocess.Popen")
def test_get_logs(mock_popen, log_service):
    """Should return the logs as a string."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"test log output", b"")
    mock_popen.return_value = mock_process

    logs = log_service.get_logs()

    assert logs == "test log output"
    mock_popen.assert_called()


@patch("birdnetpi.system.log_reader.subprocess.Popen")
def test_get_logs_file_not_found(mock_popen, log_service):
    """Should return an error message if journalctl or sed is not found."""
    mock_popen.side_effect = FileNotFoundError

    logs = log_service.get_logs()

    assert "journalctl or sed not found" in logs
