"""Tests for services API routes."""

from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.system.system_control import SystemControlService
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.system_api_routes import router


@pytest.fixture
def mock_system_control():
    """Create mock system control service."""
    return MagicMock(spec=SystemControlService)


@pytest.fixture
def client(path_resolver, mock_system_control):
    """Create test client with services API routes.

    Mocks deployment environment to consistently return "docker" so tests
    use the docker service configuration (where "fastapi" is a critical service).
    This prevents test failures in CI where systemd detection would return "sbc".
    """
    # Mock deployment environment to return "docker" consistently
    with patch(
        "birdnetpi.web.routers.system_api_routes.SystemUtils.get_deployment_environment",
        return_value="docker",
    ):
        app = FastAPI()
        container = Container()
        # IMPORTANT: Override path_resolver BEFORE any other providers to prevent permission errors
        container.path_resolver.override(providers.Singleton(lambda: path_resolver))
        container.database_path.override(
            providers.Factory(lambda: path_resolver.get_database_path())
        )
        container.system_control_service.override(providers.Object(mock_system_control))
        container.wire(modules=["birdnetpi.web.routers.system_api_routes"])
        app.include_router(router, prefix="/api")
        yield TestClient(app)


class TestSystemServicesAPIRoutes:
    """Test class for services API endpoints."""

    def test_get_services_status_success(self, client, mock_system_control):
        """Should return services status successfully."""
        mock_services = [
            {
                "name": "fastapi",
                "status": "active",
                "description": "Web interface and API",
                "pid": 1234,
                "uptime_seconds": 3600,
                "uptime_formatted": "1 hour",
                "critical": True,
                "optional": False,
            },
            {
                "name": "audio_capture",
                "status": "active",
                "description": "Audio recording service",
                "pid": 5678,
                "uptime_seconds": 7200,
                "uptime_formatted": "2 hours",
                "critical": False,
                "optional": False,
            },
        ]
        mock_system_info = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day",
            "reboot_available": True,
            "deployment_type": "docker",
        }
        mock_system_control.get_all_services_status.return_value = mock_services
        mock_system_control.get_system_info.return_value = mock_system_info
        response = client.get("/api/system/services/status")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "system" in data
        assert len(data["services"]) == 2
        assert data["services"][0]["name"] == "fastapi"
        assert (
            "day" in data["system"]["uptime_formatted"] or ":" in data["system"]["uptime_formatted"]
        )

    def test_service_action_start_success(self, client, mock_system_control):
        """Should start a service successfully."""
        mock_system_control.start_service.return_value = None
        response = client.post("/api/system/services/audio_analysis/start", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "started successfully" in data["message"]
        mock_system_control.start_service.assert_called_once_with("audio_analysis")

    def test_service_action_stop_success(self, client, mock_system_control):
        """Should stop a service successfully."""
        mock_system_control.stop_service.return_value = None
        response = client.post("/api/system/services/audio_capture/stop", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stopped successfully" in data["message"]
        mock_system_control.stop_service.assert_called_once_with("audio_capture")

    def test_service_action_restart_success(self, client, mock_system_control):
        """Should restart a critical service successfully."""
        mock_system_control.restart_service.return_value = None
        response = client.post("/api/system/services/fastapi/restart", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "restarted successfully" in data["message"]
        mock_system_control.restart_service.assert_called_once_with("fastapi")

    def test_service_action_invalid_action(self, client):
        """Should reject invalid service action."""
        response = client.post("/api/system/services/audio_capture/invalid", json={"confirm": True})
        assert response.status_code == 422

    def test_service_action_without_confirmation(self, client, mock_system_control):
        """Should require confirmation for critical service actions."""
        response = client.post("/api/system/services/fastapi/stop", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "critical" in data["message"].lower()
        assert "confirmation" in data["message"].lower()
        mock_system_control.stop_service.assert_not_called()

    def test_service_action_failure(self, client, mock_system_control):
        """Should handle service action failure."""
        mock_system_control.restart_service.side_effect = Exception("Service failed")
        response = client.post(
            "/api/system/services/audio_analysis/restart", json={"confirm": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Service failed" in data["message"]

    def test_reload_configuration_success(self, client, mock_system_control):
        """Should reload configuration successfully."""
        mock_system_control.daemon_reload.return_value = None
        response = client.post("/api/system/services/reload-config")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "reloaded successfully" in data["message"]
        mock_system_control.daemon_reload.assert_called_once()

    def test_reload_configuration_failure(self, client, mock_system_control):
        """Should handle configuration reload failure."""
        mock_system_control.daemon_reload.side_effect = Exception("Reload failed")
        response = client.post("/api/system/services/reload-config")
        assert response.status_code == 500
        assert "Reload failed" in response.json()["detail"]

    def test_reboot_system_success(self, client, mock_system_control):
        """Should initiate system reboot successfully."""
        mock_system_control.can_reboot.return_value = True
        mock_system_control.reboot_system.return_value = True
        response = client.post("/api/system/services/reboot", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reboot_initiated"] is True
        assert "initiated" in data["message"]
        mock_system_control.reboot_system.assert_called_once()

    def test_reboot_system_without_confirmation(self, client, mock_system_control):
        """Should require confirmation for system reboot."""
        response = client.post("/api/system/services/reboot", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["reboot_initiated"] is False
        assert "confirmation" in data["message"].lower()
        mock_system_control.reboot_system.assert_not_called()

    def test_reboot_system_failure(self, client, mock_system_control):
        """Should handle reboot failure gracefully."""
        mock_system_control.can_reboot.return_value = True
        mock_system_control.reboot_system.return_value = False
        response = client.post("/api/system/services/reboot", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["reboot_initiated"] is False
        assert "failed" in data["message"].lower() or "not supported" in data["message"].lower()

    def test_get_system_info_only(self, client, mock_system_control):
        """Should get system info endpoint."""
        mock_system_info = {
            "uptime_seconds": 3600,
            "uptime_formatted": "1:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }
        mock_system_control.get_system_info.return_value = mock_system_info
        response = client.get("/api/system/services/info")
        assert response.status_code == 200
        data = response.json()
        assert data["uptime_formatted"] == "1:00:00"
        assert data["deployment_type"] in ["docker", "sbc", "unknown"]
        assert data["reboot_available"] is True

    def test_service_action_with_exception(self, client, mock_system_control):
        """Should handle exceptions in service actions gracefully."""
        mock_system_control.start_service.side_effect = Exception("Test error")
        response = client.post("/api/system/services/audio_capture/start", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Test error" in data["message"]

    def test_reboot_system_not_available(self, client, mock_system_control):
        """Should handle when reboot is not available."""
        mock_system_control.can_reboot.return_value = False
        response = client.post("/api/system/services/reboot", json={"confirm": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["reboot_initiated"] is False
        assert "not available" in data["message"]
        mock_system_control.reboot_system.assert_not_called()

    def test_get_services_list(self, client):
        """Should return simplified list of services."""
        response = client.get("/api/system/services")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "total" in data
        assert isinstance(data["services"], list)
        assert data["total"] > 0
        for service in data["services"]:
            assert "name" in service
            assert "running" in service
            assert "status" in service
        service_names = [s["name"] for s in data["services"]]
        assert any(name in service_names for name in ["fastapi", "birdnetpi-fastapi"])
