"""Tests for services API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio
from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.utils.auth import AdminUser, AuthService, pwd_context
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def mock_system_control():
    """Create mock system control service."""
    return MagicMock(spec=SystemControlService)


@pytest.fixture
async def client(path_resolver, mock_system_control, authenticate_sync_client):
    """Create test client with services API routes.

    Mocks deployment environment to consistently return "docker" so tests
    use the docker service configuration (where "fastapi" is a critical service).
    This prevents test failures in CI where systemd detection would return "sbc".

    Uses app_with_temp_data infrastructure for proper authentication.
    """
    # Mock deployment environment to return "docker" consistently
    with patch(
        "birdnetpi.web.routers.system_api_routes.SystemUtils.get_deployment_environment",
        return_value="docker",
    ):
        # Override Container class-level providers BEFORE app creation
        # This is critical because create_app() uses the global Container singleton
        Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
        Container.database_path.override(
            providers.Factory(lambda: path_resolver.get_database_path())
        )

        # Create config
        manager = ConfigManager(path_resolver)
        test_config = manager.load()
        Container.config.override(providers.Singleton(lambda: test_config))

        # Create a test database service with the temp path
        temp_db_service = CoreDatabaseService(path_resolver.get_database_path())
        await temp_db_service.initialize()
        Container.core_database.override(providers.Singleton(lambda: temp_db_service))

        # Mock cache service
        mock_cache = MagicMock(spec=Cache)
        mock_cache.configure_mock(
            **{"get.return_value": None, "set.return_value": True, "ping.return_value": True}
        )
        Container.cache_service.override(providers.Singleton(lambda: mock_cache))

        # Mock redis client with in-memory storage for sessions
        mock_redis = AsyncMock(spec=redis.asyncio.Redis)
        redis_storage = {}

        async def mock_set(key, value, ex=None):
            redis_storage[key] = value
            return True

        async def mock_get(key):
            return redis_storage.get(key)

        async def mock_delete(key):
            redis_storage.pop(key, None)
            return True

        mock_redis.set = AsyncMock(spec=object, side_effect=mock_set)
        mock_redis.get = AsyncMock(spec=object, side_effect=mock_get)
        mock_redis.delete = AsyncMock(spec=object, side_effect=mock_delete)
        mock_redis.close = AsyncMock(spec=object)
        Container.redis_client.override(providers.Singleton(lambda: mock_redis))

        # Mock auth service
        mock_auth_service = MagicMock(spec=AuthService)
        mock_auth_service.admin_exists.return_value = True
        mock_admin = AdminUser(
            username="admin",
            password_hash=pwd_context.hash("testpassword"),
            created_at=datetime.now(UTC),
        )
        mock_auth_service.load_admin_user.return_value = mock_admin
        mock_auth_service.verify_password.side_effect = lambda plain, hashed: pwd_context.verify(
            plain, hashed
        )
        Container.auth_service.override(providers.Singleton(lambda: mock_auth_service))

        # Override system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create app with full auth setup
        app = create_app()

        # Create client and authenticate
        test_client = TestClient(app)
        authenticate_sync_client(test_client)
        yield test_client

        # Cleanup database
        if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
            await temp_db_service.async_engine.dispose()

        # Cleanup: reset all overrides
        Container.path_resolver.reset_override()
        Container.database_path.reset_override()
        Container.config.reset_override()
        Container.core_database.reset_override()
        Container.cache_service.reset_override()
        Container.redis_client.reset_override()
        Container.auth_service.reset_override()
        Container.system_control_service.reset_override()


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
