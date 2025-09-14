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

    def test_hardware_status_endpoint_integration(self, integration_client):
        """Should enhanced hardware status endpoint with real DI."""
        response = integration_client.get("/api/system/hardware/status")

        assert response.status_code == 200
        data = response.json()

        # Check health summary fields
        assert "components" in data
        assert "overall_status" in data

        # Check new comprehensive fields
        assert "system_info" in data
        assert "resources" in data
        assert "total_detections" in data

        # Verify system_info structure
        assert "device_name" in data["system_info"]
        assert "uptime_days" in data["system_info"]

        # Verify resources structure
        assert "cpu" in data["resources"]
        assert "memory" in data["resources"]
        assert "disk" in data["resources"]


class TestDependencyInjectionValidation:
    """Tests to validate dependency injection is configured correctly."""

    def test_detection_query_service_is_directly_injected(self, integration_client):
        """Should ensure DetectionQueryService is properly injected."""
        # This is a meta-test that verifies our architecture

        # The /api/system/hardware/status endpoint should use DetectionQueryService directly
        response = integration_client.get("/api/system/hardware/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_detections" in data

    def test_correct_types_are_injected(self, integration_app):
        """Should inject correct types from DI container.

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
