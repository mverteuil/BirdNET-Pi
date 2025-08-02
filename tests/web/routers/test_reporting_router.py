from unittest.mock import MagicMock

import pytest
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.web.main import app


@pytest.fixture(autouse=True)
def mock_app_state_managers(file_path_resolver):
    """Fixture to mock app.state managers for testing purposes."""
    # Create mock objects
    mock_detections = MagicMock()
    mock_config = MagicMock()
    # Use the real file_path_resolver fixture
    mock_file_resolver = file_path_resolver
    mock_plotting_manager = MagicMock()
    mock_data_preparation_manager = MagicMock()
    mock_location_service = MagicMock()

    # Set app.state.templates to a real Jinja2Templates instance
    app.state.templates = Jinja2Templates(directory=file_path_resolver.get_templates_dir())

    # Configure mock_detections methods as needed by ReportingManager
    mock_detections.get_detections_by_date_range.return_value = []  # Default empty list

    # Configure mock_config attributes as needed by ReportingManager
    mock_config.site_name = "Test Site"
    mock_config.latitude = 0.0
    mock_config.longitude = 0.0
    mock_config.sf_threshold = 0.0
    mock_config.privacy_threshold = 0.0
    mock_config.min_confidence = 0.0
    mock_config.min_detections = 0
    mock_config.species_chart_limit = 0
    mock_config.week_filter = False
    mock_config.scientific_names = False
    mock_config.common_names = False
    mock_config.date_format = "%Y-%m-%d"
    mock_config.time_format = "%H:%M:%S"
    mock_config.audio_format = "mp3"
    mock_config.extraction_length = 3.0
    mock_config.data = MagicMock()
    mock_config.data.extracted_dir = "/tmp/extracted"
    mock_config.data.db_path = "/tmp/test.db"
    mock_config.logging = MagicMock()
    mock_config.logging.log_level = "INFO"
    mock_config.logging.syslog_enabled = False
    mock_config.logging.file_logging_enabled = False
    mock_config.logging.log_file_path = "/tmp/test.log"
    mock_config.logging.max_log_file_size_mb = 10
    mock_config.logging.log_file_backup_count = 5

    # Store original app.state attributes
    original_detections = app.state.detections if hasattr(app.state, "detections") else None
    original_config = app.state.config if hasattr(app.state, "config") else None
    original_file_resolver = (
        app.state.file_resolver if hasattr(app.state, "file_resolver") else None
    )
    original_plotting_manager = (
        app.state.plotting_manager if hasattr(app.state, "plotting_manager") else None
    )
    original_data_preparation_manager = (
        app.state.data_preparation_manager
        if hasattr(app.state, "data_preparation_manager")
        else None
    )
    original_location_service = (
        app.state.location_service if hasattr(app.state, "location_service") else None
    )

    # Assign mock objects to app.state
    app.state.detections = mock_detections
    app.state.config = mock_config
    app.state.file_resolver = mock_file_resolver
    app.state.plotting_manager = mock_plotting_manager
    app.state.data_preparation_manager = mock_data_preparation_manager
    app.state.location_service = mock_location_service

    yield

    # Restore original app.state attributes after the test
    if original_detections is not None:
        app.state.detections = original_detections
    else:
        del app.state.detections
    if original_config is not None:
        app.state.config = original_config
    else:
        del app.state.config
    if original_file_resolver is not None:
        app.state.file_resolver = original_file_resolver
    else:
        del app.state.file_resolver
    if original_plotting_manager is not None:
        app.state.plotting_manager = original_plotting_manager
    else:
        del app.state.plotting_manager
    if original_data_preparation_manager is not None:
        app.state.data_preparation_manager = original_data_preparation_manager
    else:
        del app.state.data_preparation_manager
    if original_location_service is not None:
        app.state.location_service = original_location_service
    else:
        del app.state.location_service


client = TestClient(app)


def test_get_best_recordings(mock_app_state_managers):
    """Should retrieve the best recordings successfully."""
    # Configure the mock_detections to return test data for best recordings
    app.state.detections.get_best_detections.return_value = [
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

    response = client.get("/best_recordings")

    # Assert the response
    assert response.status_code == 200
    assert "Best Recordings" in response.text
    assert "Northern Cardinal" in response.text

    # Assert that get_best_detections was called
    app.state.detections.get_best_detections.assert_called_once()


def test_get_todays_detections(mock_app_state_managers):
    """Should retrieve today's detections successfully."""
    # Configure the mock_db_manager to return test data
    app.state.detections.get_detections_by_date_range.return_value = [
        {
            "Date": "2025-07-26",
            "Time": "12:00:00",
            "Sci_Name": "Zenaida macroura",
            "Com_Name": "Mourning Dove",
            "Confidence": 0.85,
            "Lat": 38.8951,
            "Lon": -77.0364,
        }
    ]

    response = client.get("/reports/todays_detections")

    # Assert the response
    assert response.status_code == 200
    assert "Today's Detections" in response.text
    assert "Mourning Dove" in response.text

    # Assert that get_detections_by_date_range was called
    app.state.detections.get_detections_by_date_range.assert_called_once()
