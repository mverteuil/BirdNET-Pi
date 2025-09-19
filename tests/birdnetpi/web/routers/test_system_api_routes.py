"""Tests for system API routes that handle hardware monitoring and system status."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app

# Note: HardwareMonitorManager has been replaced with SystemInspector static methods


@pytest.fixture
def mock_detection_query_service():
    """Create a mock DetectionQueryService.

    This fixture creates the mock and handles cleanup.
    """
    mock = MagicMock(spec=DetectionQueryService)
    mock.count_detections = AsyncMock(return_value=1234)
    yield mock
    # No cleanup needed - mock is garbage collected


@pytest.fixture
async def app_with_system_router(path_resolver, mock_detection_query_service):
    """Create FastAPI app with mocked detection query service.

    This fixture overrides the detection query service BEFORE creating the app,
    ensuring the mock is properly wired.
    """
    # Override Container providers BEFORE creating app
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))

    # Create config
    manager = ConfigManager(path_resolver)
    test_config = manager.load()
    Container.config.override(providers.Singleton(lambda: test_config))

    # Create database service
    temp_db_service = CoreDatabaseService(path_resolver.get_database_path())
    await temp_db_service.initialize()
    Container.core_database.override(providers.Singleton(lambda: temp_db_service))

    # Override detection query service with our mock
    Container.detection_query_service.override(providers.Object(mock_detection_query_service))

    # NOW create the app with all overrides in place
    app = create_app()
    app._test_db_service = temp_db_service  # type: ignore[attr-defined]
    app._test_mock_query_service = mock_detection_query_service  # type: ignore[attr-defined]

    yield app

    # Cleanup
    if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
        await temp_db_service.async_engine.dispose()

    # Reset overrides
    Container.path_resolver.reset_override()
    Container.database_path.reset_override()
    Container.config.reset_override()
    Container.core_database.reset_override()
    Container.detection_query_service.reset_override()


@pytest.fixture
def client(app_with_system_router):
    """Create test client."""
    return TestClient(app_with_system_router)


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client, mocker, mock_detection_query_service):
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

        response = client.get("/api/system/hardware/status")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["system_info"]["device_name"] == "Test Device"
        assert data["system_info"]["uptime_days"] == 1  # (1086400 - 1000000) / 86400
        assert data["resources"]["cpu"]["percent"] == 25.0
        assert data["total_detections"] == 1234

        # Verify the mock was called
        mock_detection_query_service.count_detections.assert_called_once()
