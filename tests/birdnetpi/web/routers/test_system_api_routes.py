"""Tests for system API routes that handle hardware monitoring and system status."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.detections.queries import DetectionQueryService

# Note: HardwareMonitorManager has been replaced with SystemInspector static methods


@pytest.fixture
def app_with_system_router(app_with_temp_data):
    """Create FastAPI app with system router and DI container."""
    app = app_with_temp_data

    if hasattr(app, "container"):
        # Note: SystemInspector uses static methods, no mocking needed at container level
        # Previously mocked hardware_monitor_manager is no longer needed

        # Mock detection query service for system overview endpoint
        mock_query_service = MagicMock(spec=DetectionQueryService)
        mock_query_service.count_detections = AsyncMock(return_value=0)
        app.container.detection_query_service.override(mock_query_service)  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app_with_system_router):
    """Create test client."""
    return TestClient(app_with_system_router)


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client, mocker):
        """Should return comprehensive system hardware status."""
        mock_health = {
            "components": {"cpu": {"status": "healthy"}},
            "overall_status": "healthy",
        }
        mock_info = {
            "device_name": "Test Device",
            "platform": "Linux",
            "cpu_count": 4,
            "boot_time": 1000000,
            "cpu_percent": 25.0,
            "cpu_temperature": 45.0,
            "memory": {
                "total": 8000000000,
                "used": 4000000000,
                "free": 4000000000,
                "percent": 50.0,
            },
            "disk": {
                "total": 100000000000,
                "used": 50000000000,
                "free": 50000000000,
                "percent": 50.0,
            },
        }

        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.time.time", return_value=1086400
        )  # 10 days after boot
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_health_summary",
            return_value=mock_health,
        )
        mocker.patch(
            "birdnetpi.web.routers.system_api_routes.SystemInspector.get_system_info",
            return_value=mock_info,
        )

        # Configure mock detection query service
        client.app.container.detection_query_service().count_detections = AsyncMock(
            return_value=1234
        )  # type: ignore[attr-defined]

        response = client.get("/api/system/hardware/status")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["system_info"]["device_name"] == "Test Device"
        assert data["system_info"]["uptime_days"] == 1  # (1086400 - 1000000) / 86400
        assert data["resources"]["cpu"]["percent"] == 25.0
        assert data["total_detections"] == 1234
