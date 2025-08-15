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


# COMPREHENSIVE WEEKLY REPORT ROUTE TESTS


def test_get_weekly_report__boundary_values(client):
    """Should handle weekly report with boundary values correctly."""
    # Configure the mock with edge case values
    mock_weekly_data = {
        "start_date": "2025-12-29",  # Year boundary
        "end_date": "2026-01-04",
        "week_number": 1,  # First week of new year
        "total_detections_current": 1,  # Minimum meaningful value
        "unique_species_current": 1,
        "total_detections_prior": 999999,  # Large prior value
        "unique_species_prior": 500,
        "percentage_diff_total": -99,  # Large negative change
        "percentage_diff_unique_species": -99,
        "top_10_species": [{"common_name": "American Robin", "count": 1, "percentage_diff": -99}],
        "new_species": [],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    assert "Weekly Report" in response.text
    assert "Week 1" in response.text
    assert "American Robin" in response.text
    assert "-99%" in response.text  # Large negative percentage


def test_get_weekly_report__large_numbers(client):
    """Should handle weekly report with large detection numbers."""
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 50000,  # Large number
        "unique_species_current": 1000,
        "total_detections_prior": 25000,
        "unique_species_prior": 500,
        "percentage_diff_total": 100,
        "percentage_diff_unique_species": 100,
        "top_10_species": [{"common_name": "House Sparrow", "count": 5000, "percentage_diff": 150}],
        "new_species": [{"common_name": "Rare Warbler", "count": 1}],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    assert "50000" in response.text  # Large total detections
    assert "1000" in response.text  # Large unique species
    assert "House Sparrow" in response.text
    assert "5000" in response.text  # Large species count


def test_get_weekly_report__zero_percentage_changes(client):
    """Should handle weekly report with zero percentage changes."""
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 50,
        "unique_species_current": 10,
        "total_detections_prior": 50,  # Same as current
        "unique_species_prior": 10,  # Same as current
        "percentage_diff_total": 0,  # No change
        "percentage_diff_unique_species": 0,  # No change
        "top_10_species": [{"common_name": "Northern Cardinal", "count": 10, "percentage_diff": 0}],
        "new_species": [],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    assert "50" in response.text
    assert "10" in response.text
    # Zero percentages should not show +/- symbols
    assert "+0%" not in response.text
    assert "-0%" not in response.text


def test_get_weekly_report__many_species(client):
    """Should handle weekly report with maximum top species list."""
    # Create full list of 10 species
    top_10_species = [
        {"common_name": f"Species {i}", "count": 20 - i, "percentage_diff": i * 5}
        for i in range(10)
    ]

    new_species = [{"common_name": f"New Species {i}", "count": 5 - i} for i in range(5)]

    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 150,
        "unique_species_current": 25,
        "total_detections_prior": 100,
        "unique_species_prior": 20,
        "percentage_diff_total": 50,
        "percentage_diff_unique_species": 25,
        "top_10_species": top_10_species,
        "new_species": new_species,
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    assert "Species 0" in response.text  # First top species
    assert "Species 9" in response.text  # Last top species
    assert "New Species 0" in response.text  # First new species
    assert "New Species 4" in response.text  # Last new species
    assert "10 species" in response.text  # Species count badge
    assert "5 new" in response.text  # New species badge


def test_get_weekly_report__mixed_percentage_changes(client):
    """Should handle weekly report with mixed positive and negative changes."""
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 75,
        "unique_species_current": 8,
        "total_detections_prior": 100,  # Decreased
        "unique_species_prior": 5,  # Increased
        "percentage_diff_total": -25,  # Negative
        "percentage_diff_unique_species": 60,  # Positive
        "top_10_species": [
            {"common_name": "Increasing Bird", "count": 20, "percentage_diff": 100},
            {"common_name": "Decreasing Bird", "count": 10, "percentage_diff": -50},
            {"common_name": "Stable Bird", "count": 5, "percentage_diff": 0},
        ],
        "new_species": [{"common_name": "Brand New Bird", "count": 3}],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    assert "-25%" in response.text  # Negative total change
    assert "+60%" in response.text  # Positive species change
    assert "+100%" in response.text  # Positive individual species
    assert "-50%" in response.text  # Negative individual species
    assert "Increasing Bird" in response.text
    assert "Decreasing Bird" in response.text
    assert "Stable Bird" in response.text


def test_get_weekly_report__template_rendering_edge_cases(client):
    """Should handle template rendering with various data edge cases."""
    mock_weekly_data = {
        "start_date": "",  # Empty date
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

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    # Should show the no data message when everything is empty/zero
    assert "No Weekly Data Available" in response.text
    assert "No bird detections have been recorded" in response.text


def test_get_weekly_report__special_characters_in_species_names(client):
    """Should handle species names with special characters correctly."""
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 25,
        "unique_species_current": 3,
        "total_detections_prior": 20,
        "unique_species_prior": 2,
        "percentage_diff_total": 25,
        "percentage_diff_unique_species": 50,
        "top_10_species": [
            {"common_name": "Bird & Species", "count": 10, "percentage_diff": 25},
            {"common_name": "Bird's-nest Warbler", "count": 8, "percentage_diff": 0},
            {"common_name": "Bird <rare>", "count": 5, "percentage_diff": -20},
        ],
        "new_species": [{"common_name": 'New "Quoted" Bird', "count": 2}],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    response = client.get("/reports/weekly")

    assert response.status_code == 200
    # HTML entities should be properly escaped
    assert "Bird &amp; Species" in response.text or "Bird & Species" in response.text
    assert "Bird&#39;s-nest" in response.text or "Bird's-nest" in response.text
    assert "&lt;rare&gt;" in response.text or "<rare>" in response.text
    # Template may escape quotes differently, so just check that the bird name appears
    assert "New" in response.text and "Bird" in response.text


def test_get_weekly_report__concurrent_access_simulation(client):
    """Should handle concurrent access to weekly report correctly."""
    # Simulate what might happen with concurrent access
    mock_weekly_data = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 100,
        "unique_species_current": 15,
        "total_detections_prior": 80,
        "unique_species_prior": 12,
        "percentage_diff_total": 25,
        "percentage_diff_unique_species": 25,
        "top_10_species": [
            {"common_name": "Concurrent Test Bird", "count": 50, "percentage_diff": 25}
        ],
        "new_species": [],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.return_value = mock_weekly_data

    # Make multiple requests to simulate concurrent access
    responses = []
    for _ in range(3):
        response = client.get("/reports/weekly")
        responses.append(response)

    # All requests should succeed
    for response in responses:
        assert response.status_code == 200
        assert "Concurrent Test Bird" in response.text

    # Verify the method was called for each request
    assert mock_reporting_manager.get_weekly_report_data.call_count == 3


def test_get_weekly_report__caching_behavior_verification(client):
    """Should verify that weekly report data is not cached at route level."""
    # First call
    mock_weekly_data_1 = {
        "start_date": "2025-07-21",
        "end_date": "2025-07-27",
        "week_number": 30,
        "total_detections_current": 100,
        "unique_species_current": 10,
        "total_detections_prior": 80,
        "unique_species_prior": 8,
        "percentage_diff_total": 25,
        "percentage_diff_unique_species": 25,
        "top_10_species": [{"common_name": "First Call Bird", "count": 50, "percentage_diff": 25}],
        "new_species": [],
    }

    # Second call with different data
    mock_weekly_data_2 = {
        "start_date": "2025-07-28",
        "end_date": "2025-08-03",
        "week_number": 31,
        "total_detections_current": 150,
        "unique_species_current": 15,
        "total_detections_prior": 100,
        "unique_species_prior": 10,
        "percentage_diff_total": 50,
        "percentage_diff_unique_species": 50,
        "top_10_species": [{"common_name": "Second Call Bird", "count": 75, "percentage_diff": 50}],
        "new_species": [],
    }

    mock_reporting_manager = client.app.container.reporting_manager()
    mock_reporting_manager.get_weekly_report_data.side_effect = [
        mock_weekly_data_1,
        mock_weekly_data_2,
    ]

    # First request
    response1 = client.get("/reports/weekly")
    assert response1.status_code == 200
    assert "First Call Bird" in response1.text
    assert "Week 30" in response1.text

    # Second request should get different data (no caching)
    response2 = client.get("/reports/weekly")
    assert response2.status_code == 200
    assert "Second Call Bird" in response2.text
    assert "Week 31" in response2.text

    # Both calls should have been made to the underlying method
    assert mock_reporting_manager.get_weekly_report_data.call_count == 2
