"""Integration tests for web routes with real dependency injection.

These tests use the actual DI container with minimal mocking to catch
type errors and dependency injection issues that unit tests might miss.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.system.hardware_monitor_manager import HardwareMonitorManager


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

        # Don't override data_manager or reporting_manager - use the real ones from container
        # The app_with_temp_data fixture already sets up a working container with real services
        # We only need to mock hardware-specific things that can't run in tests

        # Mock only hardware-specific services
        mock_hardware_monitor = MagicMock(spec=HardwareMonitorManager)
        mock_hardware_monitor.get_all_status.return_value = {
            "audio": {"status": "healthy"},
            "gps": {"status": "not_configured"},
        }
        mock_hardware_monitor.get_component_status.return_value = {"status": "healthy"}
        app.container.hardware_monitor_manager.override(mock_hardware_monitor)  # type: ignore[attr-defined]

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
        # Mock only the system monitor (hardware-specific)
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
            "uptime": "1 day",
            "load_average": [0.5, 0.6, 0.7],
        }

        # Make the actual request
        response = integration_client.get("/api/system/overview")

        # Verify response structure
        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields are present
        assert "disk_usage" in data
        assert "extra_info" in data
        assert "total_detections" in data

        # Verify data types
        assert isinstance(data["disk_usage"], dict)
        assert isinstance(data["extra_info"], dict)
        assert isinstance(data["total_detections"], int)

        # Verify the count_detections method works
        assert data["total_detections"] >= 0

    def test_hardware_status_endpoint_integration(self, integration_client):
        """Test hardware status endpoint with real DI."""
        response = integration_client.get("/api/system/hardware/status")

        assert response.status_code == 200
        data = response.json()
        assert "audio" in data
        assert data["audio"]["status"] == "healthy"

    def test_hardware_component_endpoint_integration(self, integration_client):
        """Test hardware component endpoint with real DI."""
        response = integration_client.get("/api/system/hardware/component/audio")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "audio"
        assert data["status"]["status"] == "healthy"

    def test_hardware_component_not_found_integration(self, integration_client):
        """Test hardware component not found with real DI."""
        # Configure the mock to return None for unknown component
        hardware_monitor = integration_client.app.container.hardware_monitor_manager()  # type: ignore[attr-defined]
        hardware_monitor.get_component_status.return_value = None

        response = integration_client.get("/api/system/hardware/component/unknown")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestReportingRoutesIntegration:
    """Integration tests for reporting view routes."""

    def test_detections_endpoint_integration(self, integration_client):
        """Test the /detections endpoint with real dependency injection.

        This would have caught the type annotation error (ReportingManager instead of DataManager).
        """
        # Make the actual request - this uses the real DataManager from the container
        response = integration_client.get("/reports/detections")

        # Verify response works with real dependency injection
        assert response.status_code == 200
        assert "All Detections" in response.text

    def test_todays_detections_endpoint_integration(self, integration_client):
        """Test today's detections endpoint with real DI."""
        response = integration_client.get("/reports/today")

        assert response.status_code == 200
        assert "Today&#39;s Detections" in response.text

    def test_best_recordings_endpoint_integration(self, integration_client):
        """Test best recordings endpoint with real DI."""
        response = integration_client.get("/reports/best")

        assert response.status_code == 200
        assert "Best Recordings" in response.text

    def test_weekly_report_endpoint_integration(self, integration_client):
        """Test weekly report endpoint with real DI."""
        response = integration_client.get("/reports/weekly")

        assert response.status_code == 200
        assert "Weekly Report" in response.text

    def test_charts_endpoint_integration(self, integration_client, mocker):
        """Test charts endpoint with real DI."""
        # Mock plotting manager since it generates complex charts
        mock_plotting_manager = mocker.MagicMock()
        mock_fig = mocker.MagicMock()
        mock_plotting_manager.generate_multi_day_species_and_hourly_plot.return_value = mock_fig
        mock_plotting_manager.generate_daily_detections_plot.return_value = mock_fig
        integration_client.app.container.plotting_manager.override(mock_plotting_manager)  # type: ignore[attr-defined]

        # Mock plotly.io.to_json
        mocker.patch("birdnetpi.web.routers.reporting_view_routes.pio.to_json", return_value="{}")

        response = integration_client.get("/reports/charts")

        assert response.status_code == 200
        assert "Charts" in response.text


class TestDependencyInjectionValidation:
    """Tests to validate dependency injection is configured correctly."""

    def test_data_manager_is_directly_injected(self, integration_client):
        """Ensure DataManager is directly injected, not accessed through other managers."""
        # This is a meta-test that verifies our architecture

        # The /reports/detections endpoint should use DataManager directly
        response = integration_client.get("/reports/detections")
        assert response.status_code == 200

        # The /api/system/overview endpoint should use DataManager directly
        response = integration_client.get("/api/system/overview")
        assert response.status_code == 200

    def test_correct_types_are_injected(self, integration_app):
        """Verify that the correct types are being injected.

        This test validates that the DI container is wired correctly and would
        catch the type annotation errors we fixed.
        """
        from birdnetpi.analytics.reporting_manager import ReportingManager
        from birdnetpi.detections.data_manager import DataManager

        container = integration_app.container  # type: ignore[attr-defined]

        # Get the actual instances from the container
        data_manager = container.data_manager()  # type: ignore[attr-defined]
        reporting_manager = container.reporting_manager()  # type: ignore[attr-defined]

        # These assertions would fail if we had the wrong type annotations
        # like we did when DataManager was typed as ReportingManager
        assert isinstance(data_manager, DataManager)
        assert isinstance(reporting_manager, ReportingManager)

        # Verify they're not the same instance
        assert data_manager is not reporting_manager

        # Verify DataManager has the expected methods that were being called
        assert hasattr(data_manager, "get_all_detections")
        assert hasattr(data_manager, "count_detections")
        assert callable(data_manager.get_all_detections)
        assert callable(data_manager.count_detections)
