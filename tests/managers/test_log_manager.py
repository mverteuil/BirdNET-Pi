from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.managers.log_manager import LogManager


@pytest.fixture
def log_manager():
    """Provide a LogManager instance for testing."""
    return LogManager()


@patch("birdnetpi.managers.log_manager.subprocess.Popen")
def test_get_logs_success(mock_popen, log_manager):
    """Should return the logs as a string."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"test log output", b"")
    mock_popen.return_value = mock_process

    logs = log_manager.get_logs()

    assert logs == "test log output"
    mock_popen.assert_called()


@patch("birdnetpi.managers.log_manager.subprocess.Popen")
def test_get_logs_file_not_found(mock_popen, log_manager):
    """Should return an error message if journalctl or sed is not found."""
    mock_popen.side_effect = FileNotFoundError

    logs = log_manager.get_logs()

    assert "journalctl or sed not found" in logs
