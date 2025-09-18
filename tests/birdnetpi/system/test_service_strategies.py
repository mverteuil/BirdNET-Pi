import os
import subprocess
from datetime import datetime
from unittest.mock import Mock, mock_open, patch

import pytest

from birdnetpi.system.service_strategies import (
    DockerSupervisordStrategy,
    EmbeddedSystemdStrategy,
    ServiceManagementStrategy,
    ServiceStrategySelector,
)


class TestServiceManagementStrategy:
    """Tests for the ServiceManagementStrategy abstract base class."""

    def test_should_raise_type__error_on_instantiation(self):
        """Should raise TypeError if ServiceManagementStrategy is instantiated directly."""
        with pytest.raises(TypeError):
            ServiceManagementStrategy()  # type: ignore[abstract]


class TestEmbeddedSystemdStrategy:
    """Tests for the EmbeddedSystemdStrategy implementation."""

    @patch("subprocess.run")
    def test_should_start_service(self, mock_run):
        """Should call systemctl start for the given service."""
        strategy = EmbeddedSystemdStrategy()
        strategy.start_service("test_service")
        mock_run.assert_called_once_with(["sudo", "systemctl", "start", "test_service"], check=True)

    @patch("subprocess.run")
    def test_should_stop_service(self, mock_run):
        """Should call systemctl stop for the given service."""
        strategy = EmbeddedSystemdStrategy()
        strategy.stop_service("test_service")
        mock_run.assert_called_once_with(["sudo", "systemctl", "stop", "test_service"], check=True)

    @patch("subprocess.run")
    def test_should_restart_service(self, mock_run):
        """Should call systemctl restart for the given service."""
        strategy = EmbeddedSystemdStrategy()
        strategy.restart_service("test_service")
        mock_run.assert_called_once_with(
            ["sudo", "systemctl", "restart", "test_service"], check=True
        )

    @patch("subprocess.run")
    def test_should_enable_service(self, mock_run):
        """Should call systemctl enable for the given service."""
        strategy = EmbeddedSystemdStrategy()
        strategy.enable_service("test_service")
        mock_run.assert_called_once_with(
            ["sudo", "systemctl", "enable", "test_service"], check=True
        )

    @patch("subprocess.run")
    def test_should_disable_service(self, mock_run):
        """Should call systemctl disable for the given service."""
        strategy = EmbeddedSystemdStrategy()
        strategy.disable_service("test_service")
        mock_run.assert_called_once_with(
            ["sudo", "systemctl", "disable", "test_service"], check=True
        )

    @patch("subprocess.run")
    def test_should_get_service_status_active(self, mock_run):
        """Should return 'active' for an active service."""
        mock_run.return_value.stdout = "active\n"
        mock_run.return_value.returncode = 0
        strategy = EmbeddedSystemdStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "active"
        mock_run.assert_called_once_with(
            ["systemctl", "is-active", "test_service"],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="cmd", returncode=3, stdout="inactive\n", stderr=""
        ),
    )
    def test_should_get_service_status_inactive(self, mock_run):
        """Should return 'inactive' for an inactive service."""
        strategy = EmbeddedSystemdStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "inactive"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_should_handle_systemctl_not_found(self, mock_run):
        """Should handle FileNotFoundError when systemctl is not found."""
        strategy = EmbeddedSystemdStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "error"

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["systemctl"]))
    def test_should_handle_systemctl_command_error(self, mock_run, caplog):
        """Should handle CalledProcessError from systemctl command (covers lines 51-52)."""
        strategy = EmbeddedSystemdStrategy()
        strategy.start_service("test_service")
        assert "Error starting service test_service" in caplog.text

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_should_handle_systemctl_not_found_in_command(self, mock_run, caplog):
        """Should handle FileNotFoundError from systemctl command (covers lines 53-54)."""
        strategy = EmbeddedSystemdStrategy()
        strategy.start_service("test_service")
        assert "systemctl command not found" in caplog.text

    @patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="cmd", returncode=5, stdout="failed\n", stderr=""
        ),
    )
    def test_should_get_service_status_unknown(self, mock_run):
        """Should return 'unknown' for unknown service status (covers line 90)."""
        strategy = EmbeddedSystemdStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "unknown"

    @patch("subprocess.run")
    def test_should_reload_daemon(self, mock_run):
        """Should call systemctl daemon-reload."""
        strategy = EmbeddedSystemdStrategy()
        strategy.daemon_reload()
        mock_run.assert_called_once_with(["sudo", "systemctl", "daemon-reload"], check=True)

    @patch("subprocess.run")
    def test_should_get_service_details_with_full_info(self, mock_run):
        """Should parse service details from systemctl show output."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "ActiveState=active\n"
            "MainPID=1234\n"
            "ActiveEnterTimestamp=Wed 2024-01-15 10:30:45 UTC\n"
            "SubState=running\n"
        )

        with patch("birdnetpi.system.service_strategies.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, 11, 30, 45)
            mock_datetime.strptime = datetime.strptime

            strategy = EmbeddedSystemdStrategy()
            details = strategy.get_service_details("test_service")

        assert details["name"] == "test_service"
        assert details["status"] == "active"
        assert details["pid"] == 1234
        assert details["uptime_seconds"] == 3600.0  # 1 hour difference
        assert details["sub_state"] == "running"

    @patch("subprocess.run")
    def test_should_handle_empty_timestamp(self, mock_run):
        """Should handle n/a timestamp in service details."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "ActiveState=inactive\nMainPID=0\nActiveEnterTimestamp=n/a\n"

        strategy = EmbeddedSystemdStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "inactive"
        assert details["pid"] is None
        assert details["uptime_seconds"] is None

    @patch("subprocess.run")
    def test_should_handle_service_details_error(self, mock_run, caplog):
        """Should handle errors when getting service details."""
        mock_run.side_effect = Exception("Connection error")

        strategy = EmbeddedSystemdStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "error"
        assert details["pid"] is None
        assert "Error getting service details" in caplog.text

    def test_should_get_system_uptime_from_proc(self):
        """Should read system uptime from /proc/uptime."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="12345.67 98765.43"):
                strategy = EmbeddedSystemdStrategy()
                uptime = strategy.get_system_uptime()
                assert uptime == 12345.67

    def test_should_handle_missing_proc_uptime(self):
        """Should return 0 when /proc/uptime doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            strategy = EmbeddedSystemdStrategy()
            uptime = strategy.get_system_uptime()
            assert uptime == 0.0

    def test_should_handle_proc_uptime_error(self, caplog):
        """Should handle errors when reading /proc/uptime."""
        with patch("pathlib.Path.exists", side_effect=Exception("Permission denied")):
            strategy = EmbeddedSystemdStrategy()
            uptime = strategy.get_system_uptime()
            assert uptime == 0.0
            assert "Error getting system uptime" in caplog.text

    @patch("subprocess.run")
    def test_should_reboot_system(self, mock_run):
        """Should call systemctl reboot."""
        strategy = EmbeddedSystemdStrategy()
        result = strategy.reboot_system()
        mock_run.assert_called_once_with(["sudo", "systemctl", "reboot"], check=True)
        assert result is True

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["sudo", "systemctl"]))
    def test_should_handle_reboot_failure(self, mock_run, caplog):
        """Should handle reboot command failure."""
        strategy = EmbeddedSystemdStrategy()
        result = strategy.reboot_system()
        assert result is False
        assert "Failed to reboot system" in caplog.text

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_should_handle_systemctl_not_found_on_reboot(self, mock_run, caplog):
        """Should handle missing systemctl on reboot."""
        strategy = EmbeddedSystemdStrategy()
        result = strategy.reboot_system()
        assert result is False
        assert "systemctl command not found" in caplog.text

    def test_parse_systemd_timestamp_with_valid_format(self):
        """Should parse valid systemd timestamp."""
        strategy = EmbeddedSystemdStrategy()

        with patch("birdnetpi.system.service_strategies.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, 11, 30, 45)
            mock_datetime.strptime = datetime.strptime

            uptime_seconds, start_time = strategy._parse_systemd_timestamp(
                "Wed 2024-01-15 10:30:45 UTC"
            )

        assert uptime_seconds == 3600.0
        assert start_time == "2024-01-15T10:30:45"

    def test_parse_systemd_timestamp_with_invalid_format(self):
        """Should handle invalid timestamp format."""
        strategy = EmbeddedSystemdStrategy()
        uptime_seconds, start_time = strategy._parse_systemd_timestamp("invalid")
        assert uptime_seconds is None
        assert start_time is None

    def test_parse_systemctl_output_with_malformed_lines(self):
        """Should handle malformed lines in systemctl output."""
        strategy = EmbeddedSystemdStrategy()
        details = {"status": "unknown"}

        # Test with lines without '=' separator
        strategy._parse_systemctl_output("InvalidLine\nAnother", details)
        assert details["status"] == "unknown"  # Should remain unchanged


class TestDockerSupervisordStrategy:
    """Tests for the DockerSupervisordStrategy implementation."""

    @patch("subprocess.run")
    def test_should_start_service(self, mock_run):
        """Should call supervisorctl start for the given service."""
        strategy = DockerSupervisordStrategy()
        strategy.start_service("test_service")
        mock_run.assert_called_once_with(["supervisorctl", "start", "test_service"], check=True)

    @patch("subprocess.run")
    def test_should_stop_service(self, mock_run):
        """Should call supervisorctl stop for the given service."""
        strategy = DockerSupervisordStrategy()
        strategy.stop_service("test_service")
        mock_run.assert_called_once_with(["supervisorctl", "stop", "test_service"], check=True)

    @patch("subprocess.run")
    def test_should_restart_service(self, mock_run):
        """Should call supervisorctl restart for the given service."""
        strategy = DockerSupervisordStrategy()
        strategy.restart_service("test_service")
        mock_run.assert_called_once_with(["supervisorctl", "restart", "test_service"], check=True)

    def test_should_inform_on_enable_service(self, caplog):
        """Should log an informative message for enable_service."""
        import logging

        caplog.set_level(logging.INFO)
        strategy = DockerSupervisordStrategy()
        strategy.enable_service("test_service")
        assert "not directly supported" in caplog.text

    def test_should_inform_on_disable_service(self, caplog):
        """Should log an informative message for disable_service."""
        import logging

        caplog.set_level(logging.INFO)
        strategy = DockerSupervisordStrategy()
        strategy.disable_service("test_service")
        assert "not directly supported" in caplog.text

    @patch("subprocess.run")
    def test_should_get_service_status_running(self, mock_run):
        """Should return status for a running service."""
        mock_run.return_value.stdout = (
            "test_service                 RUNNING   pid 1234, uptime 0:01:00\n"
        )
        mock_run.return_value.returncode = 0
        strategy = DockerSupervisordStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "active"
        mock_run.assert_called_once_with(
            ["supervisorctl", "status", "test_service"],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="cmd", returncode=1, stdout="test_service                 STOPPED\n", stderr=""
        ),
    )
    def test_should_get_service_status_stopped(self, mock_run):
        """Should return 'inactive' for a stopped service."""
        strategy = DockerSupervisordStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "inactive"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_should_handle_supervisorctl_not_found(self, mock_run):
        """Should handle FileNotFoundError when supervisorctl is not found."""
        strategy = DockerSupervisordStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "error"

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["supervisorctl"]))
    def test_should_handle_supervisorctl_command_error(self, mock_run, caplog):
        """Should handle CalledProcessError from supervisorctl command (covers lines 104-105)."""
        strategy = DockerSupervisordStrategy()
        strategy.start_service("test_service")
        assert "Error starting service test_service via supervisorctl" in caplog.text

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_should_handle_supervisorctl_not_found_in_command(self, mock_run, caplog):
        """Should handle FileNotFoundError from supervisorctl command (covers lines 106-109)."""
        strategy = DockerSupervisordStrategy()
        strategy.start_service("test_service")
        assert (
            "supervisorctl command not found. Is Supervisord installed and configured?"
            in caplog.text
        )

    @patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="cmd", returncode=1, stdout="unknown status\n", stderr=""
        ),
    )
    def test_should_get_service_status_unknown(self, mock_run):
        """Should return 'unknown' for unknown service status (covers line 156)."""
        strategy = DockerSupervisordStrategy()
        status = strategy.get_service_status("test_service")
        assert status == "unknown"

    @patch("subprocess.run")
    def test_should_reload_daemon(self, mock_run):
        """Should call supervisorctl reread and update for daemon reload."""
        strategy = DockerSupervisordStrategy()
        strategy.daemon_reload()

        # Should call both reread and update
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["supervisorctl", "reread"], check=True)
        mock_run.assert_any_call(["supervisorctl", "update"], check=True)

    @patch("subprocess.run")
    def test_should_get_service_details_with_running_status(self, mock_run):
        """Should parse service details from supervisorctl status output."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "test_service                 RUNNING   pid 1234, uptime 2:15:45:30"
        )

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["name"] == "test_service"
        assert details["status"] == "active"
        assert details["pid"] == 1234
        # 2 days, 15 hours, 45 minutes, 30 seconds
        expected_uptime = 2 * 86400 + 15 * 3600 + 45 * 60 + 30
        assert details["uptime_seconds"] == expected_uptime

    @patch("subprocess.run")
    def test_should_get_service_details_with_stopped_status(self, mock_run):
        """Should handle stopped service in details."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "test_service                 STOPPED"

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "inactive"
        assert details["pid"] is None
        assert details["uptime_seconds"] is None

    @patch("subprocess.run")
    def test_should_get_service_details_with_starting_status(self, mock_run):
        """Should handle starting service status."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "test_service                 STARTING"

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "starting"

    @patch("subprocess.run")
    def test_should_get_service_details_with_fatal_status(self, mock_run):
        """Should handle fatal service status."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "test_service                 FATAL     Exited too quickly"

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "failed"

    @patch("subprocess.run")
    def test_should_handle_service_details_error(self, mock_run, caplog):
        """Should handle errors when getting service details."""
        mock_run.side_effect = Exception("Connection error")

        strategy = DockerSupervisordStrategy()
        details = strategy.get_service_details("test_service")

        assert details["status"] == "error"
        assert details["pid"] is None
        assert "Error getting service details" in caplog.text

    def test_parse_supervisor_uptime_hhmmss(self):
        """Should parse HH:MM:SS format uptime."""
        strategy = DockerSupervisordStrategy()
        uptime = strategy._parse_supervisor_uptime("12:34:56")
        assert uptime == 12 * 3600 + 34 * 60 + 56

    def test_parse_supervisor_uptime_ddhhmmss(self):
        """Should parse DD:HH:MM:SS format uptime."""
        strategy = DockerSupervisordStrategy()
        uptime = strategy._parse_supervisor_uptime("3:12:34:56")
        assert uptime == 3 * 86400 + 12 * 3600 + 34 * 60 + 56

    def test_parse_supervisor_uptime_invalid(self):
        """Should return None for invalid uptime format."""
        strategy = DockerSupervisordStrategy()
        assert strategy._parse_supervisor_uptime("invalid") is None
        assert strategy._parse_supervisor_uptime("12:34") is None  # Too few parts
        assert strategy._parse_supervisor_uptime("12:34:56:78:90") is None  # Too many parts

    def test_parse_supervisor_status_with_short_uptime(self):
        """Should parse supervisor status with HH:MM:SS uptime."""
        strategy = DockerSupervisordStrategy()
        details = {"status": "unknown", "pid": None, "uptime_seconds": None}

        output = "test_service                 RUNNING   pid 5678, uptime 0:45:30"
        strategy._parse_supervisor_status(output, details)

        assert details["status"] == "active"
        assert details["pid"] == 5678
        assert details["uptime_seconds"] == 45 * 60 + 30

    def test_get_container_uptime_from_proc_1(self):
        """Should calculate container uptime from /proc/1 stat time."""
        strategy = DockerSupervisordStrategy()

        mock_stat = Mock()
        mock_stat.st_mtime = 1000000.0

        with patch("time.time", return_value=1100000.0):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat", return_value=mock_stat):
                    uptime = strategy.get_system_uptime()
                    assert uptime == 100000.0

    def test_get_container_uptime_invalid_range(self):
        """Should fall back to /proc/uptime for invalid container uptime."""
        strategy = DockerSupervisordStrategy()

        mock_stat = Mock()
        mock_stat.st_mtime = 1000000.0

        # Time that would give negative uptime
        with patch("time.time", return_value=999999.0):
            with patch("pathlib.Path.exists", side_effect=[True, True]):
                with patch("pathlib.Path.stat", return_value=mock_stat):
                    with patch("pathlib.Path.read_text", return_value="54321.0 12345.0"):
                        uptime = strategy.get_system_uptime()
                        assert uptime == 54321.0  # Falls back to /proc/uptime

    def test_get_container_uptime_fallback(self):
        """Should fall back to /proc/uptime when /proc/1 doesn't exist."""
        strategy = DockerSupervisordStrategy()

        with patch("pathlib.Path.exists", side_effect=[False, True]):
            with patch("pathlib.Path.read_text", return_value="98765.0 12345.0"):
                uptime = strategy.get_system_uptime()
                assert uptime == 98765.0

    def test_get_container_uptime_error(self, caplog):
        """Should handle errors and return 0."""
        strategy = DockerSupervisordStrategy()

        with patch("pathlib.Path.exists", side_effect=Exception("Permission denied")):
            uptime = strategy.get_system_uptime()
            assert uptime == 0.0
            assert "Error getting container uptime" in caplog.text

    @patch("builtins.open", new_callable=mock_open, read_data="/usr/bin/supervisord\x00")
    @patch("subprocess.run")
    def test_reboot_container_with_supervisord_as_init(self, mock_run, mock_file):
        """Should reboot container by signaling supervisord when it's PID 1."""
        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        # Should try to kill PID 1 with TERM signal
        mock_run.assert_called_once_with(["kill", "-TERM", "1"], check=True)
        assert result is True

    @patch("builtins.open", new_callable=mock_open, read_data="/bin/bash\x00")
    @patch("subprocess.run")
    def test_reboot_container_fallback_to_reboot_command(self, mock_run, mock_file):
        """Should try reboot command when supervisord is not PID 1."""
        # Since supervisord not in cmdline, it won't try kill
        # Will go straight to reboot command
        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        # Should try reboot command
        mock_run.assert_called_once_with(["reboot"], check=True)
        assert result is True

    @patch("builtins.open", new_callable=mock_open, read_data="/bin/bash\x00")
    @patch("subprocess.run")
    def test_reboot_container_fallback_to_supervisorctl_shutdown(self, mock_run, mock_file):
        """Should try supervisorctl shutdown as final fallback."""
        # Reboot command fails, supervisorctl shutdown succeeds
        mock_run.side_effect = [
            FileNotFoundError(),  # reboot command not found
            None,  # supervisorctl shutdown succeeds
        ]

        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        # Should try supervisorctl shutdown as final fallback
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["supervisorctl", "shutdown"], check=True)
        assert result is True

    @patch("builtins.open", new_callable=mock_open, read_data="/bin/bash\x00")
    @patch("subprocess.run", side_effect=Exception("All methods failed"))
    def test_reboot_container_all_methods_fail(self, mock_run, mock_file, caplog):
        """Should return False when all reboot methods fail."""
        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        assert result is False
        assert "Container reboot not supported" not in caplog.text  # Exception caught first
        assert "Failed to reboot container" in caplog.text

    @patch("builtins.open", side_effect=Exception("Cannot read /proc/1/cmdline"))
    def test_reboot_container_cannot_read_cmdline(self, mock_file, caplog):
        """Should handle error reading /proc/1/cmdline."""
        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        assert result is False
        assert "Failed to reboot container" in caplog.text

    @patch("builtins.open", new_callable=mock_open, read_data="/bin/bash\x00")
    @patch("subprocess.run")
    def test_reboot_container_all_methods_fail_gracefully(self, mock_run, mock_file, caplog):
        """Should return False when all reboot methods fail without exceptions."""
        # All methods fail with FileNotFoundError (handled gracefully)
        mock_run.side_effect = [
            FileNotFoundError(),  # reboot command not found
            FileNotFoundError(),  # supervisorctl not found
        ]

        strategy = DockerSupervisordStrategy()
        result = strategy.reboot_system()

        assert result is False
        assert "Container reboot not supported" in caplog.text


class TestServiceStrategySelector:
    """Tests for the ServiceStrategySelector."""

    @patch.dict(os.environ, {"DOCKER_CONTAINER": "true"})
    @patch("os.path.exists", return_value=True)
    def test_should_return_docker_supervisord_strategy__docker_env_var_set(self, mock_exists):
        """Should return DockerSupervisordStrategy if DOCKER_CONTAINER env var is 'true'."""
        strategy = ServiceStrategySelector.get_strategy()
        assert isinstance(strategy, DockerSupervisordStrategy)
        mock_exists.assert_not_called()  # Should short-circuit due to env var

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=True)
    def test_should_return_docker_supervisord_strategy__dockerenv_file_exists(self, mock_exists):
        """Should return DockerSupervisordStrategy if /.dockerenv file exists."""
        strategy = ServiceStrategySelector.get_strategy()
        assert isinstance(strategy, DockerSupervisordStrategy)
        mock_exists.assert_called_once_with("/.dockerenv")

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=False)
    def test_should_return_embedded_systemd_strategy_by_default(self, mock_exists):
        """Should return EmbeddedSystemdStrategy if no Docker indicators are present."""
        strategy = ServiceStrategySelector.get_strategy()
        assert isinstance(strategy, EmbeddedSystemdStrategy)
        mock_exists.assert_called_once_with("/.dockerenv")
