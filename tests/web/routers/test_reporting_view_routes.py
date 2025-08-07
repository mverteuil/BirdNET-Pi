from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def app_with_mocks(file_path_resolver):
    """Create FastAPI app with mocked services."""
    app = create_app()

    if hasattr(app, "container"):
        # Mock detection manager
        mock_detection_manager = MagicMock(spec=DetectionManager)
        mock_detection_manager.get_best_detections.return_value = []
        mock_detection_manager.get_all_detections.return_value = []
        app.container.detection_manager.override(mock_detection_manager)  # type: ignore[attr-defined]

        # Mock reporting manager
        mock_reporting_manager = MagicMock(spec=ReportingManager)
        mock_reporting_manager.detection_manager = mock_detection_manager
        app.container.reporting_manager.override(mock_reporting_manager)  # type: ignore[attr-defined]

        # Override file resolver
        app.container.file_resolver.override(file_path_resolver)  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app_with_mocks):
    """Create test client."""
    return TestClient(app_with_mocks)


def test_get_best_recordings(client):
    """Should retrieve the best recordings successfully."""
    # Configure the mock reporting manager to return test data for best recordings
    mock_reporting_manager = client.app.container.reporting_manager()  # type: ignore[attr-defined]
    mock_reporting_manager.get_best_detections.return_value = [
        {
            "date": "2025-07-26",
            "time": "10:00:00",
            "scientific_name": "Cardinalis cardinalis",
            "common_name": "Northern Cardinal",
            "confidence": 0.9,
            "latitude": 38.8951,
            "longitude": -77.0364,
            "species_confidence_threshold": 0.5,
            "week": 1,
            "sensitivity_setting": 1.0,
            "overlap": 0.0,
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
            "date": "2025-07-26",
            "time": "10:00:00",
            "scientific_name": "Zenaida macroura",
            "common_name": "Mourning Dove",
            "confidence": 0.85,
            "latitude": 38.8951,
            "longitude": -77.0364,
        }
    ]

    # Mock get_todays_detections since that's what the route calls
    mock_reporting_manager = client.app.container.reporting_manager()  # type: ignore[attr-defined]
    mock_reporting_manager.get_todays_detections.return_value = mock_detections

    response = client.get("/reports/today")

    # Assert the response
    assert response.status_code == 200
    assert "Today's Detections" in response.text
    assert "Mourning Dove" in response.text

    # Assert that get_todays_detections was called
    mock_reporting_manager.get_todays_detections.assert_called_once()
