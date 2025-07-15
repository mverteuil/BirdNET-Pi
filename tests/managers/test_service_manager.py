from unittest.mock import patch

import pytest

from birdnetpi.managers.service_manager import ServiceManager


@pytest.fixture
def service_manager():
    """Provide a ServiceManager instance for testing."""
    return ServiceManager()


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_restart_service_success(mock_run, service_manager):
    """Should restart a service successfully."""
    service_name = "test_service"
    service_manager.restart_service(service_name)
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "restart", service_name], check=True
    )


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_stop_service_success(mock_run, service_manager):
    """Should stop a service successfully."""
    service_name = "test_service"
    service_manager.stop_service(service_name)
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "stop", service_name], check=True
    )


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_start_service_success(mock_run, service_manager):
    """Should start a service successfully."""
    service_name = "test_service"
    service_manager.start_service(service_name)
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "start", service_name], check=True
    )


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_enable_service_success(mock_run, service_manager):
    """Should enable a service successfully."""
    service_name = "test_service"
    service_manager.enable_service(service_name)
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "enable", service_name], check=True
    )


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_disable_service_success(mock_run, service_manager):
    """Should disable a service successfully."""
    service_name = "test_service"
    service_manager.disable_service(service_name)
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "disable", service_name], check=True
    )


@patch("birdnetpi.managers.service_manager.subprocess.run")
def test_restart_services_success(mock_run, service_manager):
    """Should restart multiple services successfully."""
    services = ["test_service1", "test_service2"]
    service_manager.restart_services(services)
    assert mock_run.call_count == 2
