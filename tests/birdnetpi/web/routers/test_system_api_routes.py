"""Tests for system API routes that handle hardware monitoring and system status."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio
from dependency_injector import providers
from fastapi.testclient import TestClient
from starlette.authentication import AuthCredentials, AuthenticationBackend, SimpleUser
from starlette.requests import HTTPConnection

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.utils.auth import AuthService
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


class TestAuthBackend(AuthenticationBackend):
    """Test authentication backend that always authenticates as admin."""

    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, SimpleUser] | None:
        """Return authenticated admin user for tests."""
        return AuthCredentials(["authenticated"]), SimpleUser("test-admin")


@pytest.fixture
def mock_detection_query_service():
    """Create a mock DetectionQueryService.

    This fixture creates the mock and handles cleanup.
    """
    mock = MagicMock(
        spec=DetectionQueryService, count_detections=AsyncMock(spec=callable, return_value=1234)
    )
    yield mock


@pytest.fixture
async def app_with_system_router(path_resolver, mock_detection_query_service):
    """Create FastAPI app with mocked detection query service.

    This fixture overrides the detection query service BEFORE creating the app,
    ensuring the mock is properly wired.
    """
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))
    manager = ConfigManager(path_resolver)
    test_config = manager.load()
    Container.config.override(providers.Singleton(lambda: test_config))
    temp_db_service = CoreDatabaseService(path_resolver.get_database_path())
    await temp_db_service.initialize()
    Container.core_database.override(providers.Singleton(lambda: temp_db_service))
    Container.detection_query_service.override(providers.Object(mock_detection_query_service))

    # Mock Redis client with spec
    mock_redis = MagicMock(spec=redis.asyncio.Redis)
    Container.redis_client.override(providers.Singleton(lambda: mock_redis))

    # Mock auth_service to always return True for admin_exists()
    mock_auth_service = MagicMock(spec=AuthService)
    mock_auth_service.admin_exists.return_value = True
    Container.auth_service.override(providers.Singleton(lambda: mock_auth_service))

    # Patch SessionAuthBackend to use TestAuthBackend for authentication
    with patch("birdnetpi.web.core.factory.SessionAuthBackend", TestAuthBackend):
        app = create_app()

    app._test_db_service = temp_db_service  # type: ignore[attr-defined]
    app._test_mock_query_service = mock_detection_query_service  # type: ignore[attr-defined]
    yield app
    if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
        await temp_db_service.async_engine.dispose()
    Container.path_resolver.reset_override()
    Container.database_path.reset_override()
    Container.config.reset_override()
    Container.core_database.reset_override()
    Container.detection_query_service.reset_override()
    Container.redis_client.reset_override()
    Container.auth_service.reset_override()


@pytest.fixture
def client(app_with_system_router):
    """Create test client."""
    return TestClient(app_with_system_router)


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client, mocker, mock_detection_query_service):
        """Should return comprehensive system hardware status."""
        mock_health = {"components": {"cpu": {"status": "healthy"}}, "overall_status": "healthy"}
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
        mocker.patch("birdnetpi.web.routers.system_api_routes.time.time", return_value=1086400)
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
        assert data["system_info"]["uptime_days"] == 1
        assert data["resources"]["cpu"]["percent"] == 25.0
        assert data["total_detections"] == 1234
        mock_detection_query_service.count_detections.assert_called_once()
