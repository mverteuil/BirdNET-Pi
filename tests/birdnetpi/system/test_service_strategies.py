"""Refactored tests for service strategies using pytest parameterization."""

import logging
import os
import subprocess
from datetime import datetime
from unittest.mock import mock_open, patch

import pytest

from birdnetpi.system.service_strategies import (
    DockerSupervisordStrategy,
    EmbeddedSystemdStrategy,
    ServiceManagementStrategy,
    ServiceStrategySelector,
)

# Type for os.stat_result mock spec
StatResult = os.stat_result


class TestServiceManagementStrategy:
    """Tests for the ServiceManagementStrategy abstract base class."""

    def test_should_raise_type_error_on_instantiation(self):
        """Should raise TypeError if ServiceManagementStrategy is instantiated directly."""
        with pytest.raises(TypeError):
            ServiceManagementStrategy()  # type: ignore[abstract]


class TestEmbeddedSystemdStrategy:
    """Tests for the EmbeddedSystemdStrategy implementation."""

    @pytest.mark.parametrize(
        "method_name,service_name,expected_command",
        [
            pytest.param(
                "start_service",
                "test_service",
                ["sudo", "systemctl", "start", "test_service"],
                id="start",
            ),
            pytest.param(
                "stop_service",
                "test_service",
                ["sudo", "systemctl", "stop", "test_service"],
                id="stop",
            ),
            pytest.param(
                "restart_service",
                "test_service",
                ["sudo", "systemctl", "restart", "test_service"],
                id="restart",
            ),
            pytest.param(
                "enable_service",
                "test_service",
                ["sudo", "systemctl", "enable", "test_service"],
                id="enable",
            ),
            pytest.param(
                "disable_service",
                "test_service",
                ["sudo", "systemctl", "disable", "test_service"],
                id="disable",
            ),
            pytest.param(
                "daemon_reload",
                None,
                ["sudo", "systemctl", "daemon-reload"],
                id="daemon_reload",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_systemd_service_commands(self, mock_run, method_name, service_name, expected_command):
        """Should call appropriate systemctl command for service operations."""
        strategy = EmbeddedSystemdStrategy()
        method = getattr(strategy, method_name)

        if service_name:
            method(service_name)
        else:
            method()

        mock_run.assert_called_once_with(expected_command, check=True)

    @pytest.mark.parametrize(
        "stdout,returncode,expected_status",
        [
            pytest.param("active\n", 0, "active", id="active"),
            pytest.param("inactive\n", 3, "inactive", id="inactive"),
            pytest.param("failed\n", 5, "unknown", id="unknown"),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_get_service_status(self, mock_run, stdout, returncode, expected_status):
        """Should return correct service status based on systemctl output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="cmd", returncode=returncode, stdout=stdout, stderr=""
        )

        strategy = EmbeddedSystemdStrategy()
        status = strategy.get_service_status("test_service")

        assert status == expected_status
        mock_run.assert_called_once_with(
            ["systemctl", "is-active", "test_service"],
            capture_output=True,
            text=True,
            check=False,
        )

    @pytest.mark.parametrize(
        "side_effect,expected_status,expected_log",
        [
            pytest.param(
                FileNotFoundError,
                "error",
                None,
                id="systemctl_not_found",
            ),
            pytest.param(
                subprocess.CalledProcessError(1, ["systemctl"]),
                None,
                "Error starting service test_service",
                id="command_error",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_service_command_errors(
        self, mock_run, side_effect, expected_status, expected_log, caplog
    ):
        """Should handle errors when executing systemctl commands."""
        mock_run.side_effect = side_effect
        strategy = EmbeddedSystemdStrategy()

        if expected_status is not None:
            status = strategy.get_service_status("test_service")
            assert status == expected_status
        else:
            strategy.start_service("test_service")
            assert expected_log in caplog.text

    @patch("subprocess.run", autospec=True)
    def test_get_service_details_with_full_info(self, mock_run):
        """Should parse service details from systemctl show output."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "ActiveState=active\n"
            "MainPID=1234\n"
            "ActiveEnterTimestamp=Wed 2024-01-15 10:30:45 UTC\n"
            "SubState=running\n"
        )

        with patch("birdnetpi.system.service_strategies.datetime", autospec=True) as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, 11, 30, 45)
            mock_datetime.strptime = datetime.strptime

            strategy = EmbeddedSystemdStrategy()
            details = strategy.get_service_details("test_service")

        assert details["name"] == "test_service"
        assert details["status"] == "active"
        assert details["pid"] == 1234
        assert details["uptime_seconds"] == 3600.0  # 1 hour difference
        assert details["sub_state"] == "running"

    @pytest.mark.parametrize(
        "stdout,expected_pid,expected_uptime",
        [
            pytest.param(
                "ActiveState=inactive\nMainPID=0\nActiveEnterTimestamp=n/a\n",
                None,
                None,
                id="inactive_service",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_get_service_details_edge_cases(self, mock_run, stdout, expected_pid, expected_uptime):
        """Should handle edge cases in service details."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = stdout

        strategy = EmbeddedSystemdStrategy()
        details = strategy.get_service_details("test_service")

        assert details["pid"] == expected_pid
        assert details["uptime_seconds"] == expected_uptime

    @pytest.mark.parametrize(
        "exists,read_text,expected_uptime",
        [
            pytest.param(True, "12345.67 98765.43", 12345.67, id="proc_exists"),
            pytest.param(False, None, 0.0, id="proc_missing"),
        ],
    )
    def test_get_system_uptime(self, exists, read_text, expected_uptime):
        """Should read system uptime from /proc/uptime."""
        with patch("pathlib.Path.exists", return_value=exists):
            if exists:
                with patch("pathlib.Path.read_text", return_value=read_text):
                    strategy = EmbeddedSystemdStrategy()
                    uptime = strategy.get_system_uptime()
            else:
                strategy = EmbeddedSystemdStrategy()
                uptime = strategy.get_system_uptime()

        assert uptime == expected_uptime

    @pytest.mark.parametrize(
        "side_effect,expected_result,expected_log",
        [
            pytest.param(
                None,
                True,
                None,
                id="success",
            ),
            pytest.param(
                subprocess.CalledProcessError(1, ["sudo", "systemctl"]),
                False,
                "Failed to reboot system",
                id="reboot_failure",
            ),
            pytest.param(
                FileNotFoundError,
                False,
                "systemctl command not found",
                id="systemctl_not_found",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_reboot_system(self, mock_run, side_effect, expected_result, expected_log, caplog):
        """Should handle various reboot scenarios."""
        mock_run.side_effect = side_effect
        strategy = EmbeddedSystemdStrategy()
        result = strategy.reboot_system()

        assert result == expected_result
        if expected_log:
            assert expected_log in caplog.text
        if side_effect is None:
            mock_run.assert_called_once_with(["sudo", "systemctl", "reboot"], check=True)


class TestDockerSupervisordStrategy:
    """Tests for the DockerSupervisordStrategy implementation."""

    @pytest.mark.parametrize(
        "method_name,service_name,expected_command",
        [
            pytest.param(
                "start_service",
                "test_service",
                ["supervisorctl", "start", "test_service"],
                id="start",
            ),
            pytest.param(
                "stop_service",
                "test_service",
                ["supervisorctl", "stop", "test_service"],
                id="stop",
            ),
            pytest.param(
                "restart_service",
                "test_service",
                ["supervisorctl", "restart", "test_service"],
                id="restart",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_supervisor_service_commands(
        self, mock_run, method_name, service_name, expected_command
    ):
        """Should call appropriate supervisorctl command for service operations."""
        strategy = DockerSupervisordStrategy()
        method = getattr(strategy, method_name)
        method(service_name)
        mock_run.assert_called_once_with(expected_command, check=True)

    @pytest.mark.parametrize(
        "method_name,expected_log",
        [
            pytest.param("enable_service", "not directly supported", id="enable"),
            pytest.param("disable_service", "not directly supported", id="disable"),
        ],
    )
    def test_unsupported_operations(self, method_name, expected_log, caplog):
        """Should log informative message for unsupported operations."""
        caplog.set_level(logging.INFO)
        strategy = DockerSupervisordStrategy()
        method = getattr(strategy, method_name)
        method("test_service")
        assert expected_log in caplog.text

    @pytest.mark.parametrize(
        "stdout,returncode,expected_status",
        [
            pytest.param(
                "test_service                 RUNNING   pid 1234, uptime 0:01:00\n",
                0,
                "active",
                id="running",
            ),
            pytest.param(
                "test_service                 STOPPED\n",
                1,
                "inactive",
                id="stopped",
            ),
            pytest.param(
                "unknown status\n",
                1,
                "unknown",
                id="unknown",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_get_service_status(self, mock_run, stdout, returncode, expected_status):
        """Should return correct service status based on supervisorctl output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="cmd", returncode=returncode, stdout=stdout, stderr=""
        )

        strategy = DockerSupervisordStrategy()
        status = strategy.get_service_status("test_service")

        assert status == expected_status

    @patch("subprocess.run", autospec=True)
    def test_daemon_reload(self, mock_run):
        """Should call supervisorctl reread and update for daemon reload."""
        strategy = DockerSupervisordStrategy()
        strategy.daemon_reload()

        # Should call both reread and update
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["supervisorctl", "reread"], check=True)
        mock_run.assert_any_call(["supervisorctl", "update"], check=True)

    @pytest.mark.parametrize(
        "stdout,expected_status,expected_pid,expected_uptime",
        [
            pytest.param(
                "test_service                 RUNNING   pid 1234, uptime 2:15:45:30",
                "active",
                1234,
                2 * 86400 + 15 * 3600 + 45 * 60 + 30,
                id="running_with_uptime",
            ),
            pytest.param(
                "test_service                 STOPPED",
                "inactive",
                None,
                None,
                id="stopped",
            ),
            pytest.param(
                "test_service                 STARTING",
                "starting",
                None,
                None,
                id="starting",
            ),
            pytest.param(
                "test_service                 FATAL     Exited too quickly",
                "failed",
                None,
                None,
                id="fatal",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    def test_get_service_details(
        self, mock_run, stdout, expected_status, expected_pid, expected_uptime
    ):
        """Should parse service details from supervisorctl status output."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = stdout

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == expected_status
        assert details["pid"] == expected_pid
        assert details["uptime_seconds"] == expected_uptime

    @pytest.mark.parametrize(
        "uptime_str,expected_seconds",
        [
            pytest.param("12:34:56", 12 * 3600 + 34 * 60 + 56, id="hhmmss"),
            pytest.param("3:12:34:56", 3 * 86400 + 12 * 3600 + 34 * 60 + 56, id="ddhhmmss"),
            pytest.param("invalid", None, id="invalid"),
            pytest.param("12:34", None, id="too_few_parts"),
            pytest.param("12:34:56:78:90", None, id="too_many_parts"),
        ],
    )
    def test_parse_supervisor_uptime(self, uptime_str, expected_seconds):
        """Should parse supervisor uptime formats correctly."""
        strategy = DockerSupervisordStrategy()
        uptime = strategy._parse_supervisor_uptime(uptime_str)
        assert uptime == expected_seconds

    @pytest.mark.parametrize(
        "cmdline,reboot_method,expected_calls,expected_result",
        [
            pytest.param(
                "/usr/bin/supervisord\x00",
                "kill",
                [["kill", "-TERM", "1"]],
                True,
                id="supervisord_as_init",
            ),
            pytest.param(
                "/bin/bash\x00",
                "reboot",
                [["reboot"]],
                True,
                id="bash_use_reboot",
            ),
            pytest.param(
                "/bin/bash\x00",
                "supervisorctl_fallback",
                [["reboot"], ["supervisorctl", "shutdown"]],
                True,
                id="fallback_to_supervisorctl",
            ),
        ],
    )
    @patch("subprocess.run", autospec=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_reboot_container(
        self, mock_file, mock_run, cmdline, reboot_method, expected_calls, expected_result
    ):
        """Should handle container reboot with different methods."""
        mock_file.return_value.read.return_value = cmdline

        if reboot_method == "supervisorctl_fallback":
            # First call (reboot) fails, second (supervisorctl) succeeds
            mock_run.side_effect = [FileNotFoundError(), None]
        else:
            mock_run.return_value = None

        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        assert result == expected_result
        assert mock_run.call_count == len(expected_calls)
        for expected_call in expected_calls:
            mock_run.assert_any_call(expected_call, check=True)


class TestServiceStrategySelector:
    """Tests for the ServiceStrategySelector."""

    @pytest.mark.parametrize(
        "env_vars,dockerenv_exists,expected_strategy",
        [
            pytest.param(
                {"DOCKER_CONTAINER": "true"},
                False,
                DockerSupervisordStrategy,
                id="docker_env_var",
            ),
            pytest.param(
                {},
                True,
                DockerSupervisordStrategy,
                id="dockerenv_file",
            ),
            pytest.param(
                {},
                False,
                EmbeddedSystemdStrategy,
                id="no_docker_indicators",
            ),
        ],
    )
    @patch("os.path.exists", autospec=True)
    def test_strategy_selection(self, mock_exists, env_vars, dockerenv_exists, expected_strategy):
        """Should select correct strategy based on environment."""
        mock_exists.return_value = dockerenv_exists

        with patch.dict(os.environ, env_vars, clear=True):
            strategy = ServiceStrategySelector.get_strategy()
            assert isinstance(strategy, expected_strategy)

        if "DOCKER_CONTAINER" not in env_vars:
            mock_exists.assert_called_once_with("/.dockerenv")
        else:
            mock_exists.assert_not_called()  # Should short-circuit due to env var
