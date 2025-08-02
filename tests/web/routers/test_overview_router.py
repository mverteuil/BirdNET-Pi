"""Integration tests for overview router that exercise real endpoints and dependencies."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.web.routers.overview_router import router


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    # Initialize the database
    DatabaseService(db_path)
    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def app_with_overview_services(file_path_resolver, temp_db):
    """Create FastAPI app with overview router dependencies."""
    app = FastAPI()

    # Set up app state with minimal real components and necessary mocks
    mock_config = MagicMock()
    mock_config.data.db_path = temp_db
    app.state.config = mock_config
    # Use real detection manager with the temp database
    app.state.detections = DetectionManager(DatabaseService(temp_db))
    app.state.plotting_manager = MagicMock()  # Mock plotting manager
    app.state.file_path_resolver = file_path_resolver
    app.state.data_preparation_manager = MagicMock()  # Mock data preparation manager
    app.state.location_service = MagicMock()  # Mock location service
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_overview_services):
    """Create test client with real app."""
    return TestClient(app_with_overview_services)


class TestOverviewRouterIntegration:
    """Integration tests for overview router with real endpoints."""

    def test_overview_endpoint_returns_json(self, client):
        """Should return JSON response with system overview data."""
        response = client.get("/overview")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Check that required fields are present
        required_fields = ["disk_usage", "extra_info", "total_detections"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_overview_endpoint_disk_usage_structure(self, client):
        """Should return properly structured disk usage information."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # Verify disk usage has expected structure
        disk_usage = data["disk_usage"]
        assert isinstance(disk_usage, dict)
        # SystemMonitorService should return disk usage information

    def test_overview_endpoint_extra_info_structure(self, client):
        """Should return system extra info."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # Verify extra info exists (content depends on system)
        extra_info = data["extra_info"]
        assert isinstance(extra_info, dict)

    def test_overview_endpoint_total_detections(self, client, temp_db):
        """Should return total detections from real detection manager."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # With empty database, should return 0 detections
        assert data["total_detections"] == 0
        assert isinstance(data["total_detections"], int)

    def test_overview_uses_real_system_monitor(self, client):
        """Should use real SystemMonitorService for system information."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # Real SystemMonitorService should provide actual system data
        # The exact content varies by system, but should be present
        assert "disk_usage" in data
        assert "extra_info" in data

    def test_overview_uses_real_detection_manager(self, client, temp_db):
        """Should use real DetectionManager with actual database."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # Should connect to real database and return actual count
        assert isinstance(data["total_detections"], int)
        assert data["total_detections"] >= 0

    def test_overview_endpoint_integration_flow(self, client):
        """Should integrate all dependencies correctly."""
        response = client.get("/overview")

        assert response.status_code == 200
        data = response.json()

        # Integration test: all components should work together
        # - SystemMonitorService provides system info
        # - ReportingManager with DetectionManager provides detection count
        # - All data combined into single response

        assert len(data) == 3  # Should have exactly 3 top-level fields
        assert all(field in data for field in ["disk_usage", "extra_info", "total_detections"])
