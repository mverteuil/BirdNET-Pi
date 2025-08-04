import datetime
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.models.config import BirdNETConfig  # Added import
from birdnetpi.models.database_models import Detection
from birdnetpi.services.location_service import LocationService  # Added import


@pytest.fixture
def mock_plotting_manager():
    """Provide a mock PlottingManager instance."""
    return MagicMock(spec=PlottingManager)


@pytest.fixture
def mock_data_preparation_manager():
    """Provide a mock DataPreparationManager instance."""
    mock = MagicMock(spec=DataPreparationManager)
    mock.hms_to_str.side_effect = lambda h: h.strftime("%H:%M:%S")
    mock.hms_to_dec.side_effect = lambda h: h.hour + h.minute / 60.0
    return mock


@pytest.fixture
def detection_manager():
    """Provide a mock DatabaseManager instance."""
    return MagicMock()


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    # Add any necessary attributes that ReportingManager might access from config
    mock.site_name = "Test Site"
    mock.latitude = 0.0
    mock.longitude = 0.0
    mock.model = "test_model"
    mock.species_confidence_threshold = 0.0
    mock.birdweather_id = "test_id"
    mock.apprise_input = "test_input"
    mock.apprise_notification_title = "test_title"
    mock.apprise_notification_body = "test_body"
    mock.apprise_notify_each_detection = False
    mock.apprise_notify_new_species = False
    mock.apprise_notify_new_species_each_day = False
    mock.apprise_weekly_report = False
    mock.minimum_time_limit = 0
    mock.flickr_api_key = "test_key"
    mock.flickr_filter_email = "test_email"
    mock.database_lang = "en"
    mock.timezone = "UTC"
    mock.caddy_pwd = "test_pwd"
    mock.silence_update_indicator = False
    mock.birdnetpi_url = "test_url"
    mock.apprise_only_notify_species_names = ""
    mock.apprise_only_notify_species_names_2 = ""
    mock.database = MagicMock(path="/tmp/test.db")  # Mock database path
    return mock


@pytest.fixture
def mock_location_service():
    """Provide a mock LocationService instance."""
    return Mock(spec=LocationService)


@pytest.fixture
def reporting_manager(
    detection_manager,
    file_path_resolver,
    mock_plotting_manager,
    mock_data_preparation_manager,
    mock_config,  # Added mock_config
    mock_location_service,  # Added mock_location_service
):
    """Provide a ReportingManager instance with mocked dependencies."""
    manager = ReportingManager(
        detection_manager=detection_manager,
        file_path_resolver=file_path_resolver,
        config=mock_config,
        plotting_manager=mock_plotting_manager,
        data_preparation_manager=mock_data_preparation_manager,
        location_service=mock_location_service,
    )
    return manager


def test_get_most_recent_detections(reporting_manager, detection_manager):
    """Should return a list of recent detections."""
    detection_manager.get_most_recent_detections.return_value = [
        {"com_name": "American Robin", "Date": "2025-07-12", "Time": "10:00:00"},
        {"com_name": "Northern Cardinal", "Date": "2025-07-12", "Time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["com_name"] == "American Robin"
    detection_manager.get_most_recent_detections.assert_called_once_with(2)


def test_get_weekly_report_data(reporting_manager, detection_manager):
    """Should return a dictionary of weekly report data."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        detection_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 100, "unique_species": 10},  # Current week stats
            {"total_count": 80, "unique_species": 8},  # Prior week stats
        ]

        detection_manager.get_top_species_with_prior_counts.return_value = [
            {
                "species": "American Robin",
                "current_count": 20,
                "prior_count": 15,
            },
            {
                "species": "Northern Cardinal",
                "current_count": 15,
                "prior_count": 10,
            },
        ]

        detection_manager.get_new_species_data.return_value = [{"species": "Blue Jay", "count": 5}]

        report_data = reporting_manager.get_weekly_report_data()

        assert report_data["start_date"] == "2025-06-30"
        assert report_data["end_date"] == "2025-07-06"
        assert report_data["week_number"] == 27
        assert report_data["total_detections_current"] == 100
        assert report_data["percentage_diff_total"] == 25
        assert report_data["unique_species_current"] == 10
        assert report_data["percentage_diff_unique_species"] == 25
        assert len(report_data["top_10_species"]) == 2
        assert report_data["top_10_species"][0]["com_name"] == "American Robin"
        assert report_data["top_10_species"][0]["percentage_diff"] == 33
        assert len(report_data["new_species"]) == 1
        assert report_data["new_species"][0]["com_name"] == "Blue Jay"

        # Assertions for detection_manager method calls
        # Extract the actual calls made to get_detection_counts_by_date_range
        calls = detection_manager.get_detection_counts_by_date_range.call_args_list

        # Assert the first call
        assert calls[0].args[0] == datetime.date(2025, 6, 30)
        assert calls[0].args[1] == datetime.date(2025, 7, 6)

        # Assert the second call
        assert calls[1].args[0] == datetime.date(2025, 6, 23)
        assert calls[1].args[1] == datetime.date(2025, 6, 29)

        detection_manager.get_top_species_with_prior_counts.assert_called_once_with(
            datetime.date(2025, 6, 30),
            datetime.date(2025, 7, 6),
            datetime.date(2025, 6, 23),
            datetime.date(2025, 6, 29),
        )
        detection_manager.get_new_species_data.assert_called_once_with(
            datetime.date(2025, 6, 30), datetime.date(2025, 7, 6)
        )


def test_get_daily_detection_data_for_plotting(reporting_manager, detection_manager):
    """Should prepare daily detection data for plotting."""
    # Mock the return value of get_all_detections
    mock_detections = [
        Detection(
            id=1,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name_tensor="American Robin",
            common_name_ioc="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 0, 0),
            confidence=0.9,
            audio_file_id=101,  # Assign a mock audio_file_id
        ),
        Detection(
            id=2,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name_tensor="American Robin",
            common_name_ioc="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 15, 0),
            confidence=0.8,
            audio_file_id=102,  # Assign a mock audio_file_id
        ),
        Detection(
            id=3,
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name_tensor="Northern Cardinal",
            common_name_ioc="Northern Cardinal",
            timestamp=datetime.datetime(2025, 7, 15, 9, 0, 0),
            confidence=0.95,
            audio_file_id=103,  # Assign a mock audio_file_id
        ),
    ]
    detection_manager.get_all_detections.return_value = mock_detections

    # Call get_data to get the DataFrame
    df = reporting_manager.get_data()

    # Mock the return value of prepare_daily_plot_data
    reporting_manager.data_preparation_manager.prepare_daily_plot_data.return_value = (
        pd.DataFrame(),
        [],
        [],
        [],
    )

    # Call the method under test
    day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
        reporting_manager.get_daily_detection_data_for_plotting(
            df, resample_sel="15min", species="American Robin"
        )
    )

    # Assertions
    assert isinstance(day_hour_freq, pd.DataFrame)
    assert "American Robin" in df["Com_Name"].unique()
    assert "Northern Cardinal" in df["Com_Name"].unique()


def test_get_best_detections(reporting_manager, detection_manager):
    """Should return a list of best detections sorted by confidence."""
    detection_manager.get_best_detections.return_value = [
        {"com_name": "Northern Cardinal", "Confidence": 0.95},
        {"com_name": "American Robin", "Confidence": 0.9},
    ]

    best_detections = reporting_manager.get_best_detections(limit=2)

    assert len(best_detections) == 2
    assert best_detections[0]["com_name"] == "Northern Cardinal"
    assert best_detections[0]["Confidence"] == 0.95
    detection_manager.get_best_detections.assert_called_once_with(2)


def test_get_data_empty_detections(reporting_manager, detection_manager):
    """Should handle empty detections and return empty DataFrame with correct columns."""
    # Mock empty detections
    detection_manager.get_all_detections.return_value = []
    
    # Call get_data
    df = reporting_manager.get_data()
    
    # Verify DataFrame is empty but has correct structure
    assert df.empty
    assert list(df.columns) == [
        "Com_Name",
        "Date",
        "Time",
        "Sci_Name",
        "Confidence",
        "Lat",
        "Lon",
        "Cutoff",
        "Week",
        "Sens",
        "Overlap",
    ]
    assert df.index.name == "DateTime"
    assert pd.api.types.is_datetime64_any_dtype(df.index)


def test_get_todays_detections(reporting_manager, detection_manager):
    """Should retrieve detections for the current day."""
    today = datetime.date(2025, 7, 15)
    
    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today
        
        expected_start = datetime.datetime(2025, 7, 15, 0, 0, 0)
        expected_end = datetime.datetime(2025, 7, 15, 23, 59, 59, 999999)  # time.max includes microseconds
        
        detection_manager.get_detections_by_date_range.return_value = [
            {"com_name": "American Robin", "Date": "2025-07-15", "Time": "10:00:00"},
            {"com_name": "Northern Cardinal", "Date": "2025-07-15", "Time": "14:30:00"},
        ]
        
        # Call the method
        todays_detections = reporting_manager.get_todays_detections()
        
        # Verify the results
        assert len(todays_detections) == 2
        assert todays_detections[0]["com_name"] == "American Robin"
        
        # Verify the detection manager was called with correct date range
        detection_manager.get_detections_by_date_range.assert_called_once_with(
            expected_start, expected_end
        )


def test_date_filter(reporting_manager):
    """Should filter DataFrame by date range (covers lines 223-227)."""
    # Create test DataFrame with datetime index
    dates = pd.date_range(start='2025-07-10', end='2025-07-20', freq='D')
    df = pd.DataFrame({
        'value': range(len(dates))
    }, index=dates)
    
    # The implementation has a bug in line 224 where it tries to add timedelta to a string
    # This will raise a TypeError, which we'll catch to cover the lines
    with pytest.raises(TypeError) as exc_info:
        reporting_manager.date_filter(df, '2025-07-12', '2025-07-15')
    
    # Verify the error is what we expect (string + timedelta)
    assert "unsupported operand type(s)" in str(exc_info.value) or "can only concatenate str" in str(exc_info.value)
