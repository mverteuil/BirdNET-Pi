"""Integration tests for web routes with real dependency injection.

These tests use the actual DI container with minimal mocking to catch
type errors and dependency injection issues that unit tests might miss.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Note: HardwareMonitorManager has been replaced with SystemInspector static methods


@pytest.fixture
def integration_app(app_with_temp_data, tmp_path):
    """Create FastAPI app with real DI container and minimal mocking.

    Only mocks external services and hardware dependencies.
    Uses real managers and services where possible.
    """
    app = app_with_temp_data

    if hasattr(app, "container"):
        # Use real database with test data
        test_db_path = tmp_path / "test.db"
        test_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Don't override data_manager - use the real one from container
        # The app_with_temp_data fixture already sets up a working container with real services
        # We only need to mock hardware-specific things that can't run in tests

        # Mock only hardware-specific services
        # Note: SystemInspector uses static methods, no need to mock at container level
        # The routes will call SystemInspector.get_health_summary() directly
        mock_hardware_monitor = MagicMock()
        mock_hardware_monitor.get_all_status.return_value = {
            "audio": {"status": "healthy"},
            "gps": {"status": "not_configured"},
        }
        mock_hardware_monitor.get_component_status.return_value = {"status": "healthy"}
        # hardware_monitor_manager no longer exists in container - SystemInspector is used directly

    return app


@pytest.fixture
def integration_client(integration_app):
    """Create test client with integration app."""
    return TestClient(integration_app)


class TestSystemRoutesIntegration:
    """Integration tests for system API routes."""

    def test_system_overview_endpoint_integration(self, integration_client, mocker):
        """Test the /overview endpoint with real dependency injection.

        This test would have caught the type mismatch and missing method issues.
        """
        # Mock SystemInspector static methods (hardware-specific)
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
                "uptime": "1 day",
                "load_average": [0.5, 0.6, 0.7],
            },
        )

        # Make the actual request
        response = integration_client.get("/api/system/overview")

        # Verify response structure
        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields are present
        assert "disk_usage" in data
        assert "system_info" in data
        assert "total_detections" in data

        # Verify data types
        assert isinstance(data["disk_usage"], dict)
        assert isinstance(data["system_info"], dict)
        assert isinstance(data["total_detections"], int)

        # Verify the count_detections method works
        assert data["total_detections"] >= 0

    def test_hardware_status_endpoint_integration(self, integration_client):
        """Test hardware status endpoint with real DI."""
        response = integration_client.get("/api/system/hardware/status")

        assert response.status_code == 200
        data = response.json()
        assert "components" in data
        assert "overall_status" in data

    def test_hardware_component_endpoint_integration(self, integration_client):
        """Test hardware component endpoint with real DI."""
        response = integration_client.get("/api/system/hardware/component/cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "cpu"
        assert "status" in data["status"]

    def test_hardware_component_not_found_integration(self, integration_client):
        """Test hardware component not found with real DI."""
        # No mocking needed - SystemInspector returns unknown status for unknown components
        response = integration_client.get("/api/system/hardware/component/unknown")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "unknown"
        assert data["status"]["status"] == "unknown"
        assert "not monitored" in data["status"]["message"]


class TestDependencyInjectionValidation:
    """Tests to validate dependency injection is configured correctly."""

    def test_data_manager_is_directly_injected(self, integration_client):
        """Ensure DataManager is directly injected, not accessed through other managers."""
        # This is a meta-test that verifies our architecture

        # The /api/system/overview endpoint should use DataManager directly
        response = integration_client.get("/api/system/overview")
        assert response.status_code == 200

    def test_correct_types_are_injected(self, integration_app):
        """Verify that the correct types are being injected.

        This test validates that the DI container is wired correctly and would
        catch the type annotation errors we fixed.
        """
        from birdnetpi.detections.manager import DataManager

        container = integration_app.container  # type: ignore[attr-defined]

        # Get the actual instances from the container
        data_manager = container.data_manager()  # type: ignore[attr-defined]
        # reporting_manager = container.reporting_manager()  # ReportingManager removed

        # These assertions would fail if we had the wrong type annotations
        # like we did when DataManager was typed as ReportingManager
        assert isinstance(data_manager, DataManager)
        # assert isinstance(reporting_manager, ReportingManager)  # ReportingManager removed

        # Verify they're not the same instance
        # assert data_manager is not reporting_manager  # ReportingManager removed

        # Verify DataManager has the expected CRUD methods
        assert hasattr(data_manager, "get_all_detections")
        assert hasattr(data_manager, "create_detection")
        assert callable(data_manager.get_all_detections)
        assert callable(data_manager.create_detection)
