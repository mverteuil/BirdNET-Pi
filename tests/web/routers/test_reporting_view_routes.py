from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager


@pytest.fixture
def app_with_mocks(app_with_temp_data):
    """Create FastAPI app with mocked services."""
    app = app_with_temp_data

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
    assert "Today&#39;s Detections" in response.text
    assert "Mourning Dove" in response.text

    # Assert that get_todays_detections was called
    mock_reporting_manager.get_todays_detections.assert_called_once()


def test_get_weekly_report(client):
    """Should retrieve weekly report data successfully."""
    # Configure the mock reporting manager to return test data
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 45,
        "unique_species_current": 12,
        "total_detections_prior": 32,
        "unique_species_prior": 8,
        "percentage_diff_total": 40,
        "percentage_diff_unique_species": 50,
        "top_10_species": [
            {"common_name": "Northern Cardinal", "count": 8, "percentage_diff": 100},
            {"common_name": "Mourning Dove", "count": 6, "percentage_diff": 20},
        ],
        "new_species": [{"common_name": "American Robin", "count": 3}],
    }

    # Mock get_weekly_report_data since that's what the route calls
    mock_reporting_manager = client.app.container.reporting_manager()  # type: ignore[attr-defined]
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    # Assert the response
    assert response.status_code == 200
    assert "Weekly Report" in response.text
    assert "Week 30" in response.text
    assert "Northern Cardinal" in response.text
    assert "American Robin" in response.text
    assert "45" in response.text  # total_detections_current
    assert "12" in response.text  # unique_species_current
    assert "+40%" in response.text  # percentage_diff_total
    assert "+50%" in response.text  # percentage_diff_unique_species

    # Assert that get_weekly_report_data was called
    mock_reporting_manager.get_weekly_report_data.assert_called_once()


def test_get_weekly_report_no_data(client):
    """Should handle empty weekly report data gracefully."""
    # Configure the mock reporting manager to return empty data
    mock_weekly_data = {
        "start_date": "",
        "end_date": "",
        "week_number": 0,
        "total_detections_current": 0,
        "unique_species_current": 0,
        "total_detections_prior": 0,
        "unique_species_prior": 0,
        "percentage_diff_total": 0,
        "percentage_diff_unique_species": 0,
        "top_10_species": [],
        "new_species": [],
    }

    # Mock get_weekly_report_data since that's what the route calls
    mock_reporting_manager = client.app.container.reporting_manager()  # type: ignore[attr-defined]
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    # Assert the response
    assert response.status_code == 200
    assert "Weekly Report" in response.text
    assert "No Weekly Data Available" in response.text
    assert "No bird detections have been recorded" in response.text

    # Assert that get_weekly_report_data was called
    mock_reporting_manager.get_weekly_report_data.assert_called_once()


def test_get_weekly_report_exception_handling(client):
    """Should handle exceptions gracefully and show empty state."""
    # Mock get_weekly_report_data to raise an exception
    mock_reporting_manager = client.app.container.reporting_manager()  # type: ignore[attr-defined]
    mock_reporting_manager.get_weekly_report_data.side_effect = Exception("Database error")

    response = client.get("/reports/weekly")

    # Assert the response shows empty state when there's an exception
    assert response.status_code == 200
    assert "Weekly Report" in response.text
    assert "No Weekly Data Available" in response.text

    # Assert that get_weekly_report_data was called
    mock_reporting_manager.get_weekly_report_data.assert_called_once()
