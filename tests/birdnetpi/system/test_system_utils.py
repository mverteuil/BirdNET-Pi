from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.system_utils import SystemUtils


@pytest.fixture
def system_utils():
    """Provide a SystemUtils instance for testing."""
    return SystemUtils()


@pytest.fixture
def test_timezone_data():
    """Provide test timezone data for various scenarios."""
    return {
        "valid_timezones": [
            "America/New_York",
            "Europe/London",
            "Asia/Tokyo",
            "Australia/Sydney",
            "UTC",
        ],
        "etc_timezone_content": "America/New_York\n",
        "timedatectl_outputs": {
            "london": "Timezone=Europe/London\n",
            "tokyo": "       Time zone: Asia/Tokyo (JST, +0900)\nTimezone=Asia/Tokyo",
            "malformed": "Some random output without timezone",
            "empty": "",
        },
        "fallback_timezone": "UTC",
    }


@pytest.fixture
def test_file_scenarios():
    """Provide test scenarios for file operations."""
    return {
        "file_not_found": FileNotFoundError("No such file or directory"),
        "permission_denied": PermissionError("Permission denied"),
        "io_error": OSError("I/O operation failed"),
        "empty_file": "",
        "whitespace_only": "   \n\t   \n",
    }


@pytest.fixture
def test_subprocess_scenarios():
    """Provide test scenarios for subprocess operations."""
    return {
        "command_not_found": FileNotFoundError("timedatectl: command not found"),
        "timeout_error": TimeoutError("Command timed out"),
        "generic_exception": Exception("Subprocess failed"),
        "successful_result": MagicMock(stdout="Timezone=Europe/London\n"),
    }


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone_from_etc_timezone(
    mock_run, mock_open, system_utils, test_timezone_data
):
    """Should return the timezone from /etc/timezone."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_timezone_data[
        "etc_timezone_content"
    ]
    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][0]  # America/New_York
    mock_run.assert_not_called()


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone_from_timedatectl(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should return the timezone from timedatectl when /etc/timezone is unavailable."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["london"]
    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][1]  # Europe/London


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone_fallback_to_utc(
    mock_run,
    mock_open,
    system_utils,
    test_timezone_data,
    test_file_scenarios,
    test_subprocess_scenarios,
):
    """Should return UTC if all other methods fail."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.side_effect = test_subprocess_scenarios["generic_exception"]
    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__empty_etc_timezone_file(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to timedatectl when /etc/timezone is empty."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_file_scenarios[
        "empty_file"
    ]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["tokyo"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][2]  # Asia/Tokyo


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__whitespace_only_etc_timezone(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to timedatectl when /etc/timezone contains only whitespace."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_file_scenarios[
        "whitespace_only"
    ]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["london"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][1]  # Europe/London


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__permission_error_etc_timezone(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to timedatectl when /etc/timezone has permission issues."""
    mock_open.side_effect = test_file_scenarios["permission_denied"]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["tokyo"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][2]  # Asia/Tokyo


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__malformed_timedatectl_output(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to UTC when timedatectl output is malformed."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["malformed"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]  # UTC


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__timedatectl_command_not_found(
    mock_run,
    mock_open,
    system_utils,
    test_timezone_data,
    test_file_scenarios,
    test_subprocess_scenarios,
):
    """Should fallback to UTC when timedatectl command is not found."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.side_effect = test_subprocess_scenarios["command_not_found"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]  # UTC


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__timedatectl_timeout(
    mock_run,
    mock_open,
    system_utils,
    test_timezone_data,
    test_file_scenarios,
    test_subprocess_scenarios,
):
    """Should fallback to UTC when timedatectl command times out."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.side_effect = test_subprocess_scenarios["timeout_error"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]  # UTC


@patch("birdnetpi.system.system_utils.open")
@patch("birdnetpi.system.system_utils.subprocess.run")
def test_get_system_timezone__io_error_reading_file(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to timedatectl when I/O error occurs reading /etc/timezone."""
    mock_open.side_effect = test_file_scenarios["io_error"]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["london"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][1]  # Europe/London
