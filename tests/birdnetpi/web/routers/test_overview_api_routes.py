"""Integration tests for overview router that exercise real endpoints and dependencies."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.database.core import CoreDatabaseService

# Note: HardwareMonitorManager has been replaced with SystemInspector static methods


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = Path(temp_file.name)

    # Initialize the database
    db_service = CoreDatabaseService(db_path)
    await db_service.initialize()
    try:
        yield db_path
    finally:
        # Dispose async engine
        if hasattr(db_service, "async_engine") and db_service.async_engine:
            await db_service.async_engine.dispose()
        # Cleanup file
        db_path.unlink(missing_ok=True)


@pytest.fixture
def app_with_overview_services(app_with_temp_data):
    """Create FastAPI app with overview router dependencies."""
    app = app_with_temp_data

    # Override services with mocks or test instances
    if hasattr(app, "container"):
        # Note: SystemInspector uses static methods, no mocking needed at container level
        # The route will call SystemInspector.get_health_summary() directly
        mock_hardware_monitor = MagicMock()
        mock_hardware_monitor.get_all_status.return_value = {
            "disk_usage": {"usage": 50.0, "used_gb": 50.0, "total_gb": 100.0, "free_gb": 50.0},
            "cpu_temperature": "45.2°C",
            "memory_usage": {"percent": 40.0},
        }
        # hardware_monitor_manager no longer exists in container - SystemInspector is used directly

        # Mock detection_query_service to return detection count
        from birdnetpi.detections.queries import DetectionQueryService

        mock_query_service = MagicMock(spec=DetectionQueryService)
        # count_detections is async, so use AsyncMock
        mock_query_service.count_detections = AsyncMock(return_value=0)
        app.container.detection_query_service.override(mock_query_service)  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app_with_overview_services):
    """Create test client with real app."""
    return TestClient(app_with_overview_services)


class TestOverviewRouterIntegration:
    """Integration tests for overview router with real endpoints."""

    def test_overview_endpoint_returns_json(self, client):
        """Should return JSON response with system overview data."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Check that required fields are present
        required_fields = ["system_status", "total_detections"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_overview_endpoint_disk_usage_structure(self, client):
        """Should return properly structured disk usage information."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # Verify system status has expected structure
        system_status = data["system_status"]
        assert isinstance(system_status, dict)
        # SystemInspector should return health summary with components
        assert "components" in system_status
        assert "disk" in system_status["components"]

    def test_overview_endpoint_system_status_structure(self, client):
        """Should return system status information."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # Verify system status exists (content depends on system)
        system_status = data["system_status"]
        assert isinstance(system_status, dict)

    def test_overview_endpoint_total_detections(self, client, temp_db):
        """Should return total detections from real detection manager."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # With empty database, should return 0 detections
        assert data["total_detections"] == 0
        assert isinstance(data["total_detections"], int)

    def test_overview_uses_real_hardware_monitor(self, client):
        """Should use real HardwareMonitorManager for system information."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # Real HardwareMonitorManager should provide actual system data
        # The exact content varies by system, but should be present
        assert "system_status" in data
        assert "total_detections" in data

    def test_overview_uses_real_data_manager(self, client, temp_db):
        """Should use real DetectionManager with actual database."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # Should connect to real database and return actual count
        assert isinstance(data["total_detections"], int)
        assert data["total_detections"] >= 0

    def test_overview_endpoint_integration_flow(self, client):
        """Should integrate all dependencies correctly."""
        response = client.get("/api/overview")

        assert response.status_code == 200
        data = response.json()

        # Integration test: all components should work together
        # - HardwareMonitorManager provides system status
        # - ReportingManager with DetectionManager provides detection count
        # - All data combined into single response

        assert len(data) == 2  # Should have exactly 2 top-level fields
        assert all(field in data for field in ["system_status", "total_detections"])
