"""Tests for system API routes that handle hardware monitoring and system status."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.detections.manager import DataManager

# Note: HardwareMonitorManager has been replaced with SystemInspector static methods


@pytest.fixture
def app_with_system_router(app_with_temp_data):
    """Create FastAPI app with system router and DI container."""
    app = app_with_temp_data

    if hasattr(app, "container"):
        # Note: SystemInspector uses static methods, no mocking needed at container level
        # Previously mocked hardware_monitor_manager is no longer needed

        # Mock data manager for system overview endpoint
        mock_data_manager = MagicMock(spec=DataManager)
        mock_data_manager.count_detections = AsyncMock(return_value=0)
        app.container.data_manager.override(mock_data_manager)  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app_with_system_router):
    """Create test client."""
    return TestClient(app_with_system_router)


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client, mocker):
        """Should return system hardware status."""
        mock_status = {
            "components": {"cpu": {"status": "healthy"}},
            "overall_status": "healthy",
        }
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_health_summary",
            return_value=mock_status,
        )

        response = client.get("/api/system/hardware/status")

        assert response.status_code == 200
        assert response.json() == mock_status

    def test_get_hardware_component(self, client, mocker):
        """Should return specific component status."""
        mock_summary = {
            "components": {"cpu": {"status": "healthy", "message": "CPU usage normal: 25%"}},
            "overall_status": "healthy",
        }
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_health_summary",
            return_value=mock_summary,
        )

        response = client.get("/api/system/hardware/component/cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "cpu"
        assert data["status"] == {"status": "healthy", "message": "CPU usage normal: 25%"}

    def test_get_hardware_component_not_found(self, client, mocker):
        """Should return status for unknown component."""
        mock_summary = {
            "components": {"cpu": {"status": "healthy"}},
            "overall_status": "healthy",
        }
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_health_summary",
            return_value=mock_summary,
        )

        response = client.get("/api/system/hardware/component/unknown")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "unknown"
        assert data["status"]["status"] == "unknown"
        assert "not monitored" in data["status"]["message"]

    def test_get_system_overview(self, client, mocker):
        """Should return system overview data including disk usage and total detections."""
        # Mock SystemInspector static methods
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_disk_usage",
            return_value={
                "total": 100000000,
                "used": 50000000,
                "free": 50000000,
                "percent": 50.0,
            },
        )
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_system_info",
            return_value={
                "uptime": "2 days",
                "load_average": [0.5, 0.6, 0.7],
            },
        )

        # Configure mock data manager
        client.app.container.data_manager().count_detections = AsyncMock(return_value=1234)  # type: ignore[attr-defined]

        response = client.get("/api/system/overview")

        assert response.status_code == 200
        data = response.json()
        assert "disk_usage" in data
        assert data["disk_usage"]["percent"] == 50.0
        assert "system_info" in data
        assert data["system_info"]["uptime"] == "2 days"
        assert "total_detections" in data
        assert data["total_detections"] == 1234

        # Verify the data manager method was called correctly
        client.app.container.data_manager().count_detections.assert_called_once()  # type: ignore[attr-defined]
