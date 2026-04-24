"""Integration tests for SystemControlService.

These tests verify actual behavior rather than just mock delegation,
including subprocess command execution, error handling, and strategy selection.
"""

import subprocess
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.service_strategies import (
    DockerSupervisordStrategy,
    EmbeddedSystemdStrategy,
    ServiceManagementStrategy,
    ServiceStrategySelector,
)
from birdnetpi.system.system_control import SystemControlService


class TestServiceStrategySelection:
    """Test that the correct strategy is selected based on environment."""

    def test_docker_strategy_selected_with_env_var(self):
        """Should select Docker strategy when DOCKER_CONTAINER=true."""
        with patch.dict("os.environ", {"DOCKER_CONTAINER": "true"}):
            strategy = ServiceStrategySelector.get_strategy()
            assert isinstance(strategy, DockerSupervisordStrategy)

    def test_docker_strategy_selected_with_dockerenv(self):
        """Should select Docker strategy when /.dockerenv exists."""
        with patch("os.path.exists", return_value=True):
            strategy = ServiceStrategySelector.get_strategy()
            assert isinstance(strategy, DockerSupervisordStrategy)

    def test_systemd_strategy_selected_by_default(self):
        """Should select systemd strategy when not in Docker."""
        with patch.dict("os.environ", clear=True), patch("os.path.exists", return_value=False):
            strategy = ServiceStrategySelector.get_strategy()
            assert isinstance(strategy, EmbeddedSystemdStrategy)


class TestSystemdStrategyCommands:
    """Test that systemd strategy executes correct commands."""

    @pytest.fixture
    def systemd_strategy(self):
        """Create systemd strategy for testing."""
        return EmbeddedSystemdStrategy()

    @pytest.mark.parametrize(
        "method_name,expected_action",
        [
            pytest.param("start_service", "start", id="start"),
            pytest.param("stop_service", "stop", id="stop"),
            pytest.param("restart_service", "restart", id="restart"),
            pytest.param("enable_service", "enable", id="enable"),
            pytest.param("disable_service", "disable", id="disable"),
        ],
    )
    def test_systemctl_commands(self, systemd_strategy, method_name, expected_action):
        """Should execute correct systemctl commands for service operations."""
        service_name = "test_service"

        with patch("subprocess.run", autospec=True) as mock_run:
            method = getattr(systemd_strategy, method_name)
            method(service_name)

            mock_run.assert_called_once_with(
                ["sudo", "systemctl", expected_action, service_name], check=True
            )

    def test_daemon_reload(self, systemd_strategy):
        """Should execute daemon-reload command."""
        with patch("subprocess.run", autospec=True) as mock_run:
            systemd_strategy.daemon_reload()

            mock_run.assert_called_once_with(["sudo", "systemctl", "daemon-reload"], check=True)

    @pytest.mark.parametrize(
        "error_type,expected_log",
        [
            pytest.param(
                subprocess.CalledProcessError(1, "cmd"),
                "Error starting service",
                id="command-error",
            ),
            pytest.param(FileNotFoundError(), "systemctl command not found", id="file-not-found"),
        ],
    )
    def test_command_error_handling(self, systemd_strategy, error_type, expected_log, caplog):
        """Should handle errors when systemctl command fails."""
        with patch("subprocess.run", autospec=True, side_effect=error_type):
            systemd_strategy.start_service("test_service")

            assert expected_log in caplog.text

    @pytest.mark.parametrize(
        "returncode,expected_status",
        [
            pytest.param(0, "active", id="active"),
            pytest.param(3, "inactive", id="inactive"),
            pytest.param(4, "unknown", id="unknown"),
        ],
    )
    def test_get_service_status(self, systemd_strategy, returncode, expected_status):
        """Should correctly parse systemctl status output."""
        mock_result = MagicMock(spec=CompletedProcess)
        mock_result.returncode = returncode

        with patch("subprocess.run", autospec=True, return_value=mock_result):
            status = systemd_strategy.get_service_status("test_service")

            assert status == expected_status

    def test_get_service_status_file_not_found(self, systemd_strategy):
        """Should handle missing systemctl command gracefully."""
        with patch("subprocess.run", autospec=True, side_effect=FileNotFoundError()):
            status = systemd_strategy.get_service_status("test_service")

            assert status == "error"

    def test_get_system_uptime(self, systemd_strategy, tmp_path):
        """Should read system uptime from /proc/uptime."""
        uptime_file = tmp_path / "uptime"
        uptime_file.write_text("12345.67 98765.43\n")

        with patch("pathlib.Path", return_value=uptime_file):
            uptime = systemd_strategy.get_system_uptime()

            assert uptime == 12345.67

    def test_reboot_system_success(self, systemd_strategy):
        """Should execute reboot command successfully."""
        with patch("subprocess.run", autospec=True) as mock_run:
            result = systemd_strategy.reboot_system()

            assert result is True
            mock_run.assert_called_once_with(["sudo", "systemctl", "reboot"], check=True)

    def test_reboot_system_failure(self, systemd_strategy):
        """Should handle reboot command failure."""
        with patch(
            "subprocess.run", autospec=True, side_effect=subprocess.CalledProcessError(1, "cmd")
        ):
            result = systemd_strategy.reboot_system()

            assert result is False


class TestSupervisordStrategyCommands:
    """Test that supervisord strategy executes correct commands."""

    @pytest.fixture
    def supervisord_strategy(self):
        """Create supervisord strategy for testing."""
        return DockerSupervisordStrategy()

    @pytest.mark.parametrize(
        "method_name,expected_action",
        [
            pytest.param("start_service", "start", id="start"),
            pytest.param("stop_service", "stop", id="stop"),
        ],
    )
    def test_supervisorctl_commands(self, supervisord_strategy, method_name, expected_action):
        """Should execute correct supervisorctl commands."""
        service_name = "test_service"

        with patch("subprocess.run", autospec=True) as mock_run:
            method = getattr(supervisord_strategy, method_name)
            method(service_name)

            mock_run.assert_called_once_with(
                ["supervisorctl", expected_action, service_name], check=True
            )

    def test_restart_uses_popen(self, supervisord_strategy):
        """Should use Popen with start_new_session for restart to allow self-restart."""
        service_name = "test_service"

        with patch("subprocess.Popen", autospec=True) as mock_popen:
            supervisord_strategy.restart_service(service_name)

            mock_popen.assert_called_once_with(
                ["supervisorctl", "restart", service_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def test_daemon_reload(self, supervisord_strategy):
        """Should execute reread and update commands."""
        with patch("subprocess.run", autospec=True) as mock_run:
            supervisord_strategy.daemon_reload()

            assert mock_run.call_count == 2
            mock_run.assert_any_call(["supervisorctl", "reread"], check=True)
            mock_run.assert_any_call(["supervisorctl", "update"], check=True)

    @pytest.mark.parametrize(
        "output,expected_status",
        [
            pytest.param("test_service RUNNING pid 1234, uptime 0:45:30", "active", id="running"),
            pytest.param("test_service STOPPED", "inactive", id="stopped"),
            pytest.param("test_service STARTING", "unknown", id="starting"),
        ],
    )
    def test_get_service_status(self, supervisord_strategy, output, expected_status):
        """Should correctly parse supervisorctl status output."""
        mock_result = MagicMock(spec=CompletedProcess)
        mock_result.stdout = output
        mock_result.returncode = 0

        with patch("subprocess.run", autospec=True, return_value=mock_result):
            status = supervisord_strategy.get_service_status("test_service")

            assert status == expected_status


class TestSystemControlService:
    """Test SystemControlService integration with strategies."""

    def test_service_control_methods_call_strategy(self):
        """Should delegate service control to strategy."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)
        service.strategy = mock_strategy

        # Test all service control methods
        service.start_service("test")
        mock_strategy.start_service.assert_called_once_with("test")

        service.stop_service("test")
        mock_strategy.stop_service.assert_called_once_with("test")

        service.restart_service("test")
        mock_strategy.restart_service.assert_called_once_with("test")

    def test_restart_services_multiple(self):
        """Should restart multiple services in sequence."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)
        service.strategy = mock_strategy

        service.restart_services(["service1", "service2", "service3"])

        assert mock_strategy.restart_service.call_count == 3
        mock_strategy.restart_service.assert_any_call("service1")
        mock_strategy.restart_service.assert_any_call("service2")
        mock_strategy.restart_service.assert_any_call("service3")

    def test_get_service_details(self):
        """Should get detailed service information."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)
        mock_strategy.get_service_details.return_value = {
            "name": "test_service",
            "status": "active",
            "pid": 1234,
            "uptime_seconds": 3600.0,
        }
        service.strategy = mock_strategy

        details = service.get_service_details("test_service")

        assert details["name"] == "test_service"
        assert details["status"] == "active"
        assert details["pid"] == 1234
        assert details["uptime_seconds"] == 3600.0

    def test_get_all_services_status(self):
        """Should get status for multiple services."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)

        def mock_get_details(service_name):
            return {"name": service_name, "status": "active", "pid": 1234}

        mock_strategy.get_service_details.side_effect = mock_get_details
        service.strategy = mock_strategy

        service_list = [
            {"name": "service1", "description": "Service 1"},
            {"name": "service2", "description": "Service 2"},
        ]

        result = service.get_all_services_status(service_list)

        assert len(result) == 2
        assert result[0]["name"] == "service1"
        assert result[0]["status"] == "active"
        assert result[0]["description"] == "Service 1"

    def test_get_system_info(self):
        """Should get system information including uptime."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)
        mock_strategy.get_system_uptime.return_value = 86400.0  # 1 day
        service.strategy = mock_strategy

        info = service.get_system_info()

        assert info["uptime_seconds"] == 86400.0
        assert "reboot_available" in info

    def test_reboot_system(self):
        """Should attempt system reboot."""
        service = SystemControlService()
        mock_strategy = MagicMock(spec=ServiceManagementStrategy)
        mock_strategy.reboot_system.return_value = True
        service.strategy = mock_strategy

        result = service.reboot_system()

        assert result is True
        mock_strategy.reboot_system.assert_called_once()


class TestSupervisorStatusParsing:
    """Test supervisor status string parsing."""

    @pytest.fixture
    def supervisord_strategy(self):
        """Create supervisord strategy for testing."""
        return DockerSupervisordStrategy()

    @pytest.mark.parametrize(
        "status_output,expected_details",
        [
            pytest.param(
                "service RUNNING   pid 1234, uptime 0:45:30",
                {"status": "active", "pid": 1234, "uptime_seconds": 2730.0},
                id="running-with-uptime",
            ),
            pytest.param(
                "service RUNNING   pid 5678, uptime 2:10:15:45",
                {"status": "active", "pid": 5678, "uptime_seconds": 209745.0},
                id="running-multi-day",
            ),
            pytest.param("service STOPPED", {"status": "inactive", "pid": None}, id="stopped"),
            pytest.param("service STARTING", {"status": "starting", "pid": None}, id="starting"),
            pytest.param("service FATAL", {"status": "failed", "pid": None}, id="fatal"),
        ],
    )
    def test_parse_supervisor_status(self, supervisord_strategy, status_output, expected_details):
        """Should correctly parse various supervisor status outputs."""
        mock_result = MagicMock(spec=CompletedProcess)
        mock_result.stdout = status_output
        mock_result.returncode = 0

        with patch("subprocess.run", autospec=True, return_value=mock_result):
            details = supervisord_strategy.get_service_details("service")

            for key, value in expected_details.items():
                assert details.get(key) == value


class TestSystemdTimestampParsing:
    """Test systemd timestamp parsing."""

    @pytest.fixture
    def systemd_strategy(self):
        """Create systemd strategy for testing."""
        return EmbeddedSystemdStrategy()

    def test_parse_systemd_timestamp_valid(self, systemd_strategy):
        """Should parse valid systemd timestamp."""
        # Freeze time for predictable testing
        timestamp = "Wed 2024-01-15 10:30:45 UTC"

        with patch("birdnetpi.system.service_strategies.datetime", autospec=True) as mock_datetime:
            from datetime import datetime

            mock_now = datetime(2024, 1, 15, 11, 30, 45)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime

            uptime_seconds, start_time = systemd_strategy._parse_systemd_timestamp(timestamp)

            assert uptime_seconds == 3600.0  # 1 hour
            assert start_time == "2024-01-15T10:30:45"

    def test_parse_systemd_timestamp_invalid(self, systemd_strategy):
        """Should handle invalid timestamp gracefully."""
        uptime_seconds, start_time = systemd_strategy._parse_systemd_timestamp("invalid")

        assert uptime_seconds is None
        assert start_time is None

    def test_parse_systemd_timestamp_empty(self, systemd_strategy):
        """Should handle empty timestamp."""
        uptime_seconds, start_time = systemd_strategy._parse_systemd_timestamp("")

        assert uptime_seconds is None
        assert start_time is None
