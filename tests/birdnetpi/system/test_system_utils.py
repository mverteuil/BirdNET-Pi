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


@pytest.mark.parametrize(
    "file_behavior,timedatectl_output,expected_timezone",
    [
        pytest.param(
            ("read", "America/New_York\n"),
            None,
            "America/New_York",
            id="from_etc_timezone",
        ),
        pytest.param(
            ("exception", FileNotFoundError()),
            "Timezone=Europe/London\n",
            "Europe/London",
            id="from_timedatectl",
        ),
        pytest.param(
            ("exception", FileNotFoundError()),
            "       Time zone: Asia/Tokyo (JST, +0900)\nTimezone=Asia/Tokyo",
            "Asia/Tokyo",
            id="complex_timedatectl_output",
        ),
        pytest.param(
            ("exception", FileNotFoundError()),
            ("exception", Exception("Command failed")),
            "UTC",
            id="fallback_to_utc",
        ),
        pytest.param(
            ("read", ""),
            None,
            "UTC",
            id="empty_etc_timezone",
        ),
        pytest.param(
            ("read", "   \n\t   \n"),
            None,
            "UTC",
            id="whitespace_only_etc_timezone",
        ),
        pytest.param(
            ("exception", PermissionError("Permission denied")),
            None,
            "UTC",
            id="permission_denied_reading_file",
        ),
        pytest.param(
            ("exception", OSError("I/O operation failed")),
            "Timezone=Europe/London\n",
            "Europe/London",
            id="io_error_reading_file",
        ),
    ],
)
@patch("birdnetpi.system.system_utils.subprocess.run", autospec=True)
@patch("builtins.open", autospec=True)
def test_get_system_timezone(
    mock_open, mock_run, system_utils, file_behavior, timedatectl_output, expected_timezone
):
    """Should return timezone from various sources with proper fallback behavior."""
    behavior_type, behavior_value = file_behavior

    if behavior_type == "exception":
        mock_open.side_effect = behavior_value
    else:  # "read"
        mock_open.return_value.__enter__.return_value.read.return_value = behavior_value

    if timedatectl_output:
        if isinstance(timedatectl_output, tuple):
            # It's an exception scenario
            _, exception = timedatectl_output
            mock_run.side_effect = exception
        else:
            # It's a normal output
            mock_run.return_value.stdout = timedatectl_output

    timezone = system_utils.get_system_timezone()
    assert timezone == expected_timezone


# Test environment detection methods


class TestDockerEnvironment:
    """Test Docker environment detection."""

    @pytest.mark.parametrize(
        "dockerenv_exists,env_var_set,expected",
        [
            (True, False, True),
            (False, True, True),
            (False, False, False),
        ],
        ids=["dockerenv_file_exists", "env_var_set", "no_indicators"],
    )
    def test_is_docker_environment(self, dockerenv_exists, env_var_set, expected):
        """Should detect Docker environment from various indicators."""
        with patch("os.path.exists", return_value=dockerenv_exists) as mock_exists:
            env = {"DOCKER_CONTAINER": "true"} if env_var_set else {}
            with patch.dict(os.environ, env, clear=True):
                result = SystemUtils.is_docker_environment()
                assert result is expected
                if dockerenv_exists:
                    mock_exists.assert_called_once_with("/.dockerenv")


class TestSystemdAvailability:
    """Test systemd availability detection."""

    @pytest.mark.parametrize(
        "returncode,exception,expected",
        [
            (0, None, True),
            (1, None, False),
            (None, FileNotFoundError(), False),
            (None, subprocess.TimeoutExpired("systemctl", 2), False),
        ],
        ids=["command_succeeds", "command_fails", "file_not_found", "timeout"],
    )
    def test_is_systemd_available(self, returncode, exception, expected):
        """Should detect systemd availability based on systemctl command."""
        with patch("subprocess.run", autospec=True) as mock_run:
            if exception:
                mock_run.side_effect = exception
            else:
                mock_run.return_value.returncode = returncode

            result = SystemUtils.is_systemd_available()
            assert result is expected

            if not exception:
                mock_run.assert_called_once_with(
                    ["systemctl", "--version"],
                    capture_output=True,
                    timeout=2,
                )


class TestGitVersion:
    """Test git version detection."""

    @pytest.mark.parametrize(
        "branch_result,commit_result,exception,expected",
        [
            ((0, "main\n"), (0, "abc12345\n"), None, "main@abc12345"),
            ((1, ""), (0, "abc12345\n"), None, "unknown@abc12345"),
            ((0, "main\n"), (1, ""), None, "main@unknown"),
            (None, None, subprocess.TimeoutExpired("git", 5), "unknown"),
            (None, None, FileNotFoundError(), "unknown"),
        ],
        ids=["success", "branch_fails", "commit_fails", "timeout", "git_not_found"],
    )
    def test_get_git_version(self, branch_result, commit_result, exception, expected):
        """Should handle various git command outcomes."""
        with patch("subprocess.run", autospec=True) as mock_run:
            if exception:
                mock_run.side_effect = exception
            else:
                branch_returncode, branch_stdout = branch_result
                commit_returncode, commit_stdout = commit_result
                mock_run.side_effect = [
                    MagicMock(
                        spec=subprocess.CompletedProcess,
                        returncode=branch_returncode,
                        stdout=branch_stdout,
                    ),
                    MagicMock(
                        spec=subprocess.CompletedProcess,
                        returncode=commit_returncode,
                        stdout=commit_stdout,
                    ),
                ]

            result = SystemUtils.get_git_version()
            assert result == expected


class TestDeploymentEnvironment:
    """Test deployment environment detection."""

    @pytest.mark.parametrize(
        "is_docker,systemd_returncode,env_var,expected",
        [
            (True, None, None, "docker"),
            (False, 0, None, "sbc"),
            (False, 1, "development", "development"),
            (False, 1, None, "unknown"),
        ],
        ids=["docker_env", "sbc_env", "development_env", "unknown_env"],
    )
    def test_get_deployment_environment(self, is_docker, systemd_returncode, env_var, expected):
        """Should detect deployment environment based on various indicators."""
        with patch("os.path.exists", return_value=False):
            env = {}
            if is_docker:
                env["DOCKER_CONTAINER"] = "true"
            if env_var:
                env["BIRDNETPI_ENV"] = env_var

            with patch.dict(os.environ, env, clear=True):
                if not is_docker and systemd_returncode is not None:
                    with patch("subprocess.run", autospec=True) as mock_run:
                        mock_run.return_value.returncode = systemd_returncode
                        result = SystemUtils.get_deployment_environment()
                else:
                    result = SystemUtils.get_deployment_environment()

                assert result == expected
