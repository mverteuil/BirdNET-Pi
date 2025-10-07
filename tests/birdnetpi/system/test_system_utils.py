import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.system_utils import SystemUtils


@pytest.fixture
def system_utils():
    """Provide a SystemUtils instance for testing."""
    return SystemUtils()


@pytest.fixture
def test_timezone_data():
    """Should provide test timezone data for various scenarios."""
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
    """Should provide test scenarios for file operations."""
    return {
        "file_not_found": FileNotFoundError("No such file or directory"),
        "permission_denied": PermissionError("Permission denied"),
        "io_error": OSError("I/O operation failed"),
        "empty_file": "",
        "whitespace_only": "   \n\t   \n",
    }


@pytest.fixture
def test_subprocess_scenarios():
    """Should provide test scenarios for subprocess operations."""
    return {
        "success": MagicMock(
            spec=subprocess.CompletedProcess, returncode=0, stdout="Success\n", stderr=""
        ),
        "failure": MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr="Error\n"
        ),
        "timeout": subprocess.TimeoutExpired("command", 10),
        "not_found": FileNotFoundError("Command not found"),
        "subprocess_error": subprocess.SubprocessError("Subprocess failed"),
    }


# Test get_system_timezone method


@patch("builtins.open", autospec=True)
def test_get_system_timezone__from_etc_timezone(mock_open, system_utils, test_timezone_data):
    """Should return timezone from /etc/timezone when file exists and is readable."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_timezone_data[
        "etc_timezone_content"
    ]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][0]  # America/New_York
    mock_open.assert_called_once_with("/etc/timezone")


@patch("builtins.open", autospec=True)
@patch("birdnetpi.system.system_utils.subprocess.run", autospec=True)
def test_get_system_timezone__from_timedatectl(
    mock_run, mock_open, system_utils, test_timezone_data
):
    """Should fallback to timedatectl when /etc/timezone is not available."""
    mock_open.side_effect = FileNotFoundError()
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["london"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][1]  # Europe/London
    mock_run.assert_called_once_with(
        ["timedatectl", "show"], capture_output=True, text=True, check=True
    )


@patch("builtins.open", autospec=True)
@patch("birdnetpi.system.system_utils.subprocess.run", autospec=True)
def test_get_system_timezone__complex_timedatectl_output(
    mock_run, mock_open, system_utils, test_timezone_data
):
    """Should parse timezone from multi-line timedatectl output."""
    mock_open.side_effect = FileNotFoundError()
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["tokyo"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][2]  # Asia/Tokyo


@patch("builtins.open", autospec=True)
@patch("birdnetpi.system.system_utils.subprocess.run", autospec=True)
def test_get_system_timezone__fallback_to_utc(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should return UTC when all detection methods fail."""
    mock_open.side_effect = test_file_scenarios["file_not_found"]
    mock_run.side_effect = Exception("Command failed")

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]


@patch("builtins.open", autospec=True)
def test_get_system_timezone__empty_etc_timezone(
    mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should try timedatectl when /etc/timezone is empty."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_file_scenarios[
        "empty_file"
    ]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]


@patch("builtins.open", autospec=True)
def test_get_system_timezone__whitespace_only_etc_timezone(
    mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should try timedatectl when /etc/timezone contains only whitespace."""
    mock_open.return_value.__enter__.return_value.read.return_value = test_file_scenarios[
        "whitespace_only"
    ]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]


@patch("builtins.open", autospec=True)
def test_get_system_timezone__permission_denied_reading_file(
    mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback when permission denied reading /etc/timezone."""
    mock_open.side_effect = test_file_scenarios["permission_denied"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["fallback_timezone"]


@patch("builtins.open", autospec=True)
@patch("birdnetpi.system.system_utils.subprocess.run", autospec=True)
def test_get_system_timezone__io_error_reading_file(
    mock_run, mock_open, system_utils, test_timezone_data, test_file_scenarios
):
    """Should fallback to timedatectl when I/O error occurs reading /etc/timezone."""
    mock_open.side_effect = test_file_scenarios["io_error"]
    mock_run.return_value.stdout = test_timezone_data["timedatectl_outputs"]["london"]

    timezone = system_utils.get_system_timezone()
    assert timezone == test_timezone_data["valid_timezones"][1]  # Europe/London


# Test environment detection methods


class TestDockerEnvironment:
    """Test Docker environment detection."""

    @patch("os.path.exists", autospec=True)
    def test_is_docker_environment__dockerenv(self, mock_exists):
        """Should return True when /.dockerenv exists."""
        mock_exists.return_value = True
        assert SystemUtils.is_docker_environment() is True
        mock_exists.assert_called_once_with("/.dockerenv")

    @patch("os.path.exists", autospec=True)
    @patch.dict(os.environ, {"DOCKER_CONTAINER": "true"})
    def test_is_docker_environment__env_var(self, mock_exists):
        """Should return True when DOCKER_CONTAINER env var is set."""
        mock_exists.return_value = False
        assert SystemUtils.is_docker_environment() is True

    @patch("os.path.exists", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_is_docker_environment__false(self, mock_exists):
        """Should return False when no Docker indicators present."""
        mock_exists.return_value = False
        assert SystemUtils.is_docker_environment() is False


class TestSystemdAvailability:
    """Test systemd availability detection."""

    @patch("subprocess.run", autospec=True)
    def test_is_systemd_available__true(self, mock_run):
        """Should return True when systemctl command succeeds."""
        mock_run.return_value.returncode = 0
        assert SystemUtils.is_systemd_available() is True
        mock_run.assert_called_once_with(
            ["systemctl", "--version"],
            capture_output=True,
            timeout=2,
        )

    @patch("subprocess.run", autospec=True)
    def test_is_systemd_available__false_command_failed(self, mock_run):
        """Should return False when systemctl command fails."""
        mock_run.return_value.returncode = 1
        assert SystemUtils.is_systemd_available() is False

    @patch("subprocess.run", autospec=True)
    def test_is_systemd_available__false_exception(self, mock_run):
        """Should return False when subprocess raises exception."""
        mock_run.side_effect = FileNotFoundError()
        assert SystemUtils.is_systemd_available() is False

    @patch("subprocess.run", autospec=True)
    def test_is_systemd_available__timeout(self, mock_run):
        """Should return False when subprocess times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("systemctl", 2)
        assert SystemUtils.is_systemd_available() is False


class TestGitVersion:
    """Test git version detection."""

    @patch("subprocess.run", autospec=True)
    def test_get_git_version__success(self, mock_run):
        """Should return formatted version when git commands succeed."""
        mock_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="main\n"),
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="abc12345\n"),
        ]
        result = SystemUtils.get_git_version()
        assert result == "main@abc12345"

    @patch("subprocess.run", autospec=True)
    def test_get_git_version__branch_failure(self, mock_run):
        """Should return 'unknown' branch name when branch command fails."""
        mock_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=1, stdout=""),
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="abc12345\n"),
        ]
        result = SystemUtils.get_git_version()
        assert result == "unknown@abc12345"

    @patch("subprocess.run", autospec=True)
    def test_get_git_version__commit_failure(self, mock_run):
        """Should return 'unknown' commit hash when commit command fails."""
        mock_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="main\n"),
            MagicMock(spec=subprocess.CompletedProcess, returncode=1, stdout=""),
        ]
        result = SystemUtils.get_git_version()
        assert result == "main@unknown"

    @patch("subprocess.run", autospec=True)
    def test_get_git_version__timeout_exception(self, mock_run):
        """Should return 'unknown' when git commands time out."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)
        result = SystemUtils.get_git_version()
        assert result == "unknown"

    @patch("subprocess.run", autospec=True)
    def test_get_git_version__file_not_found(self, mock_run):
        """Should return 'unknown' when git is not installed."""
        mock_run.side_effect = FileNotFoundError()
        result = SystemUtils.get_git_version()
        assert result == "unknown"


class TestDeploymentEnvironment:
    """Test deployment environment detection."""

    @patch("os.path.exists", autospec=True)
    @patch.dict(os.environ, {"DOCKER_CONTAINER": "true"})
    def test_get_deployment_environment__docker(self, mock_exists):
        """Should return 'docker' when in Docker environment."""
        mock_exists.return_value = False  # /.dockerenv doesn't exist
        assert SystemUtils.get_deployment_environment() == "docker"

    @patch("os.path.exists", autospec=True)
    @patch("subprocess.run", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_get_deployment_environment__sbc(self, mock_run, mock_exists):
        """Should return 'sbc' when systemd available and not in Docker."""
        mock_exists.return_value = False  # Not in Docker
        mock_run.return_value.returncode = 0  # systemd available
        assert SystemUtils.get_deployment_environment() == "sbc"

    @patch("os.path.exists", autospec=True)
    @patch("subprocess.run", autospec=True)
    @patch.dict(os.environ, {"BIRDNETPI_ENV": "development"})
    def test_get_deployment_environment__development(self, mock_run, mock_exists):
        """Should return 'development' when BIRDNETPI_ENV is set."""
        mock_exists.return_value = False  # Not in Docker
        mock_run.return_value.returncode = 1  # No systemd
        assert SystemUtils.get_deployment_environment() == "development"

    @patch("os.path.exists", autospec=True)
    @patch("subprocess.run", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_get_deployment_environment__unknown(self, mock_run, mock_exists):
        """Should return 'unknown' when no environment indicators present."""
        mock_exists.return_value = False  # Not in Docker
        mock_run.return_value.returncode = 1  # No systemd
        assert SystemUtils.get_deployment_environment() == "unknown"
