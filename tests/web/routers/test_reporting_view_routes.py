from unittest.mock import MagicMock

import pytest
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def app_with_mocks(file_path_resolver):
    """Create FastAPI app with mocked services."""
    app = create_app()
    
    if hasattr(app, 'container'):
        # Mock detection manager
        mock_detection_manager = MagicMock(spec=DetectionManager)
        mock_detection_manager.get_best_detections.return_value = []
        mock_detection_manager.get_all_detections.return_value = []
        app.container.detection_manager.override(mock_detection_manager)
        
        # Mock reporting manager
        mock_reporting_manager = MagicMock(spec=ReportingManager)
        mock_reporting_manager.detection_manager = mock_detection_manager
        app.container.reporting_manager.override(mock_reporting_manager)
        
        # Override file resolver
        app.container.file_resolver.override(file_path_resolver)
    
    return app


@pytest.fixture
def client(app_with_mocks):
    """Create test client."""
    return TestClient(app_with_mocks)


def test_get_best_recordings(client):
    """Should retrieve the best recordings successfully."""
    # Configure the mock reporting manager to return test data for best recordings
    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_best_detections.return_value = [
        {
            "Date": "2025-07-26",
            "Time": "10:00:00",
            "Sci_Name": "Cardinalis cardinalis",
            "Com_Name": "Northern Cardinal",
            "Confidence": 0.9,
            "Lat": 38.8951,
            "Lon": -77.0364,
        }
    ]

    response = client.get("/reports/best")

    # Assert the response
    assert response.status_code == 200
    assert "Best Recordings" in response.text
    assert "Northern Cardinal" in response.text

    # Assert that get_best_detections was called
    mock_reporting_manager.get_best_detections.assert_called_once()


def test_get_todays_detections(client):
    """Should retrieve today's detections successfully."""
    # Configure the mock reporting manager to return test data
    mock_detections = [
        {
            "Date": "2025-07-26",
            "Time": "10:00:00",
            "Sci_Name": "Zenaida macroura",
            "Com_Name": "Mourning Dove",
            "Confidence": 0.85,
            "Lat": 38.8951,
            "Lon": -77.0364,
        }
    ]

    # Mock get_todays_detections since that's what the route calls
    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_todays_detections.return_value = mock_detections

    response = client.get("/reports/today")

    # Assert the response
    assert response.status_code == 200
    assert "Today's Detections" in response.text
    assert "Mourning Dove" in response.text

    # Assert that get_todays_detections was called
    mock_reporting_manager.get_todays_detections.assert_called_once()
