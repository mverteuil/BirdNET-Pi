from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.services.log_service import LogService


@pytest.fixture
def log_service():
    """Provide a LogService instance for testing."""
    return LogService()


@patch("birdnetpi.services.log_service.subprocess.Popen")
def test_get_logs(mock_popen, log_service):
    """Should return the logs as a string."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"test log output", b"")
    mock_popen.return_value = mock_process

    logs = log_service.get_logs()

    assert logs == "test log output"
    mock_popen.assert_called()


@patch("birdnetpi.services.log_service.subprocess.Popen")
def test_get_logs_file_not_found(mock_popen, log_service):
    """Should return an error message if journalctl or sed is not found."""
    mock_popen.side_effect = FileNotFoundError

    logs = log_service.get_logs()

    assert "journalctl or sed not found" in logs
