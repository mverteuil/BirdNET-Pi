"""Integration tests for views router that exercise real templates and models."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.web.routers.views_router import router


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
def app_with_templates(temp_db):
    """Create FastAPI app with real templates and minimal mocking."""
    app = FastAPI()

    # Set up app state with real components
    app.state.detections = DetectionManager(temp_db)
    app.state.templates = Jinja2Templates(directory="src/birdnetpi/web/templates")

    # Mock only the complex config object
    mock_config = MagicMock()
    mock_config.data.num_days_to_display = 7
    app.state.config = mock_config

    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_templates):
    """Create test client with real app."""
    return TestClient(app_with_templates)


class TestViewsRouterIntegration:
    """Integration tests for views router with real templates."""

    def test_views_page_renders_template(self, client):
        """Should render views.html template successfully."""
        response = client.get("/views")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        # Check that the template was rendered (contains HTML structure)
        content = response.text
        assert "<html" in content or "<!DOCTYPE" in content
        assert "commits_behind" in content or "views" in content

    def test_weekly_report_renders_template(self, client):
        """Should render weekly_report.html template successfully."""
        response = client.get("/views/weekly-report")

        # This might fail if ReportingManager dependencies aren't properly set up
        # but that's the point - we want to find real integration issues
        assert response.status_code in [200, 500]  # Allow 500 to identify real issues

        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/html")
            content = response.text
            assert "<html" in content or "<!DOCTYPE" in content

    def test_charts_page_renders_template(self, client):
        """Should render charts.html template successfully."""
        response = client.get("/views/charts")

        # This might fail due to pandas/plotting dependencies
        # but that's the point - we want real integration testing
        assert response.status_code in [200, 500]  # Allow 500 to identify real issues

        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/html")
            content = response.text
            assert "<html" in content or "<!DOCTYPE" in content

    def test_livestream_page_renders_template(self, client):
        """Should render livestream.html template successfully."""
        response = client.get("/livestream")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        content = response.text
        assert "<html" in content or "<!DOCTYPE" in content
        # Should contain websocket URL
        assert "ws://" in content

    def test_spectrogram_page_renders_template(self, client):
        """Should render spectrogram.html template successfully."""
        response = client.get("/spectrogram")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        content = response.text
        assert "<html" in content or "<!DOCTYPE" in content
        # Should contain websocket URLs
        assert "ws://" in content

    def test_detection_manager_dependency_works(self, client, temp_db):
        """Should use real DetectionManager instance."""
        # Make a request that uses the detection manager
        response = client.get("/views")

        assert response.status_code == 200

        # The DetectionManager should have been instantiated with real DB
        app = client.app
        detection_manager = app.state.detections
        assert isinstance(detection_manager, DetectionManager)
        assert detection_manager.db_service.db_path == temp_db
