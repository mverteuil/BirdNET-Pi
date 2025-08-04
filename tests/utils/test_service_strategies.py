import os
import subprocess
from unittest.mock import patch

import pytest

from birdnetpi.utils.service_strategies import (
    DockerSupervisordStrategy,
    EmbeddedSystemdStrategy,
    ServiceManagementStrategy,
    ServiceStrategySelector,
)


class TestServiceManagementStrategy:
    """Tests for the ServiceManagementStrategy abstract base class."""

    def test_should_raise_type_error_on_instantiation(self):
        """Should raise TypeError if ServiceManagementStrategy is instantiated directly."""
        with pytest.raises(TypeError):
            ServiceManagementStrategy()


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
    @patch("builtins.print")
    def test_should_handle_systemctl_command_error(self, mock_print, mock_run):
        """Should handle CalledProcessError from systemctl command (covers lines 51-52)."""
        strategy = EmbeddedSystemdStrategy()
        strategy.start_service("test_service")
        mock_print.assert_called_once()
        assert "Error starting service test_service" in mock_print.call_args[0][0]

    @patch("subprocess.run", side_effect=FileNotFoundError)
    @patch("builtins.print")
    def test_should_handle_systemctl_not_found_in_command(self, mock_print, mock_run):
        """Should handle FileNotFoundError from systemctl command (covers lines 53-54)."""
        strategy = EmbeddedSystemdStrategy()
        strategy.start_service("test_service")
        mock_print.assert_called_once()
        assert "systemctl command not found" in mock_print.call_args[0][0]

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

    @patch("builtins.print")
    def test_should_inform_on_enable_service(self, mock_print):
        """Should print an informative message for enable_service."""
        strategy = DockerSupervisordStrategy()
        strategy.enable_service("test_service")
        mock_print.assert_called_once()
        assert "not directly supported" in mock_print.call_args[0][0]

    @patch("builtins.print")
    def test_should_inform_on_disable_service(self, mock_print):
        """Should print an informative message for disable_service."""
        strategy = DockerSupervisordStrategy()
        strategy.disable_service("test_service")
        mock_print.assert_called_once()
        assert "not directly supported" in mock_print.call_args[0][0]

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
    @patch("builtins.print")
    def test_should_handle_supervisorctl_command_error(self, mock_print, mock_run):
        """Should handle CalledProcessError from supervisorctl command (covers lines 104-105)."""
        strategy = DockerSupervisordStrategy()
        strategy.start_service("test_service")
        mock_print.assert_called_once()
        assert "Error starting service test_service via supervisorctl" in mock_print.call_args[0][0]

    @patch("subprocess.run", side_effect=FileNotFoundError)
    @patch("builtins.print")
    def test_should_handle_supervisorctl_not_found_in_command(self, mock_print, mock_run):
        """Should handle FileNotFoundError from supervisorctl command (covers lines 106-109)."""
        strategy = DockerSupervisordStrategy()
        strategy.start_service("test_service")
        mock_print.assert_called_once()
        assert "supervisorctl command not found" in mock_print.call_args[0][0]

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


class TestServiceStrategySelector:
    """Tests for the ServiceStrategySelector."""

    @patch.dict(os.environ, {"DOCKER_CONTAINER": "true"})
    @patch("os.path.exists", return_value=True)
    def test_should_return_docker_supervisord_strategy_if_docker_env_var_set(self, mock_exists):
        """Should return DockerSupervisordStrategy if DOCKER_CONTAINER env var is 'true'."""
        strategy = ServiceStrategySelector.get_strategy()
        assert isinstance(strategy, DockerSupervisordStrategy)
        mock_exists.assert_not_called()  # Should short-circuit due to env var

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=True)
    def test_should_return_docker_supervisord_strategy_if_dockerenv_file_exists(self, mock_exists):
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
