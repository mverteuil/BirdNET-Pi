"""Tests for system API routes that handle hardware monitoring and system status."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.system.hardware_monitor_manager import HardwareMonitorManager


@pytest.fixture
def app_with_system_router(app_with_temp_data):
    """Create FastAPI app with system router and DI container."""
    app = app_with_temp_data

    if hasattr(app, "container"):
        # Mock hardware monitor service
        mock_hardware_monitor = MagicMock(spec=HardwareMonitorManager)
        app.container.hardware_monitor_manager.override(mock_hardware_monitor)  # type: ignore[attr-defined]

        # Mock data manager for system overview endpoint
        mock_data_manager = MagicMock(spec=DataManager)
        mock_data_manager.count_detections.return_value = 0
        app.container.data_manager.override(mock_data_manager)  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app_with_system_router):
    """Create test client."""
    return TestClient(app_with_system_router)


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client):
        """Should return system hardware status."""
        mock_status = {"cpu": "healthy", "memory": "normal", "temperature": 45.2}
        client.app.container.hardware_monitor_manager().get_all_status.return_value = mock_status  # type: ignore[attr-defined]

        response = client.get("/api/system/hardware/status")

        assert response.status_code == 200
        assert response.json() == mock_status

    def test_get_hardware_component(self, client):
        """Should return specific component status."""
        mock_status = {"status": "healthy", "value": 45.2}
        client.app.container.hardware_monitor_manager().get_component_status.return_value = (  # type: ignore[attr-defined]
            mock_status
        )

        response = client.get("/api/system/hardware/component/cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "cpu"
        assert data["status"] == mock_status

    def test_get_hardware_component_not_found(self, client):
        """Should return 404 for unknown component."""
        client.app.container.hardware_monitor_manager().get_component_status.return_value = None  # type: ignore[attr-defined]

        response = client.get("/api/system/hardware/component/unknown")

        assert response.status_code == 404
        assert "Component 'unknown' not found" in response.json()["detail"]

    def test_get_system_overview(self, client, mocker):
        """Should return system overview data including disk usage and total detections."""
        # Mock SystemMonitorService (it's created directly in the route)
        mock_system_monitor = mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemMonitorService"
        )
        mock_system_monitor.return_value.get_disk_usage.return_value = {
            "total": 100000000,
            "used": 50000000,
            "free": 50000000,
            "percent": 50.0,
        }
        mock_system_monitor.return_value.get_extra_info.return_value = {
            "uptime": "2 days",
            "load_average": [0.5, 0.6, 0.7],
        }

        # Configure mock data manager
        client.app.container.data_manager().count_detections.return_value = 1234  # type: ignore[attr-defined]

        response = client.get("/api/system/overview")

        assert response.status_code == 200
        data = response.json()
        assert "disk_usage" in data
        assert data["disk_usage"]["percent"] == 50.0
        assert "extra_info" in data
        assert data["extra_info"]["uptime"] == "2 days"
        assert "total_detections" in data
        assert data["total_detections"] == 1234

        # Verify the data manager method was called correctly
        client.app.container.data_manager().count_detections.assert_called_once()  # type: ignore[attr-defined]
