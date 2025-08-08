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
    mock = MagicMock()
    # Set up detection_query_service to make reporting manager use IOC methods
    mock.detection_query_service = MagicMock()
    return mock


@pytest.fixture
def detection_manager_no_ioc():
    """Provide a mock DatabaseManager instance without IOC service."""
    mock = MagicMock()
    # Disable IOC methods to test fallback path
    mock.detection_query_service = None
    return mock


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
    detection_manager.get_most_recent_detections_with_ioc.return_value = [
        {"common_name": "American Robin", "date": "2025-07-12", "time": "10:00:00"},
        {"common_name": "Northern Cardinal", "date": "2025-07-12", "time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["common_name"] == "American Robin"
    detection_manager.get_most_recent_detections_with_ioc.assert_called_once_with(2, "en")


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
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "current_count": 20,
                "prior_count": 15,
            },
            {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
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
        assert report_data["top_10_species"][0]["common_name"] == "American Robin"
        assert report_data["top_10_species"][0]["percentage_diff"] == 33
        assert len(report_data["new_species"]) == 1
        assert report_data["new_species"][0]["common_name"] == "Blue Jay"

        # Assertions for detection_manager method calls
        # Extract the actual calls made to get_detection_counts_by_date_range
        calls = detection_manager.get_detection_counts_by_date_range.call_args_list

        # Assert the first call (expects datetime objects, not date objects)
        assert calls[0].args[0] == datetime.datetime(2025, 6, 30, 0, 0, 0)
        assert calls[0].args[1] == datetime.datetime(2025, 7, 6, 23, 59, 59, 999999)

        # Assert the second call
        assert calls[1].args[0] == datetime.datetime(2025, 6, 23, 0, 0, 0)
        assert calls[1].args[1] == datetime.datetime(2025, 6, 29, 23, 59, 59, 999999)

        detection_manager.get_top_species_with_prior_counts.assert_called_once_with(
            datetime.datetime(2025, 6, 30, 0, 0, 0),
            datetime.datetime(2025, 7, 6, 23, 59, 59, 999999),
            datetime.datetime(2025, 6, 23, 0, 0, 0),
            datetime.datetime(2025, 6, 29, 23, 59, 59, 999999),
        )
        detection_manager.get_new_species_data.assert_called_once_with(
            datetime.datetime(2025, 6, 30, 0, 0, 0),
            datetime.datetime(2025, 7, 6, 23, 59, 59, 999999),
        )


def test_get_daily_detection_data_for_plotting(reporting_manager, detection_manager):
    """Should prepare daily detection data for plotting."""
    # Mock DetectionWithIOCData objects for the IOC service
    from unittest.mock import MagicMock

    mock_detection_with_ioc_1 = MagicMock()
    mock_detection_with_ioc_1.get_best_common_name.return_value = "American Robin"
    mock_detection_with_ioc_1.timestamp = datetime.datetime(2025, 7, 15, 8, 0, 0)
    mock_detection_with_ioc_1.scientific_name = "Turdus migratorius"
    mock_detection_with_ioc_1.confidence = 0.9
    mock_detection_with_ioc_1.detection.latitude = None
    mock_detection_with_ioc_1.detection.longitude = None
    mock_detection_with_ioc_1.detection.species_confidence_threshold = 0.03
    mock_detection_with_ioc_1.detection.week = 1
    mock_detection_with_ioc_1.detection.sensitivity_setting = 1.25
    mock_detection_with_ioc_1.detection.overlap = 0.0
    mock_detection_with_ioc_1.ioc_english_name = "American Robin"
    mock_detection_with_ioc_1.translated_name = "American Robin"
    mock_detection_with_ioc_1.family = "Turdidae"
    mock_detection_with_ioc_1.genus = "Turdus"
    mock_detection_with_ioc_1.order_name = "Passeriformes"

    mock_detection_with_ioc_2 = MagicMock()
    mock_detection_with_ioc_2.get_best_common_name.return_value = "American Robin"
    mock_detection_with_ioc_2.timestamp = datetime.datetime(2025, 7, 15, 8, 15, 0)
    mock_detection_with_ioc_2.scientific_name = "Turdus migratorius"
    mock_detection_with_ioc_2.confidence = 0.8
    mock_detection_with_ioc_2.detection.latitude = None
    mock_detection_with_ioc_2.detection.longitude = None
    mock_detection_with_ioc_2.detection.species_confidence_threshold = 0.03
    mock_detection_with_ioc_2.detection.week = 1
    mock_detection_with_ioc_2.detection.sensitivity_setting = 1.25
    mock_detection_with_ioc_2.detection.overlap = 0.0
    mock_detection_with_ioc_2.ioc_english_name = "American Robin"
    mock_detection_with_ioc_2.translated_name = "American Robin"
    mock_detection_with_ioc_2.family = "Turdidae"
    mock_detection_with_ioc_2.genus = "Turdus"
    mock_detection_with_ioc_2.order_name = "Passeriformes"

    mock_detection_with_ioc_3 = MagicMock()
    mock_detection_with_ioc_3.get_best_common_name.return_value = "Northern Cardinal"
    mock_detection_with_ioc_3.timestamp = datetime.datetime(2025, 7, 15, 9, 0, 0)
    mock_detection_with_ioc_3.scientific_name = "Cardinalis cardinalis"
    mock_detection_with_ioc_3.confidence = 0.95
    mock_detection_with_ioc_3.detection.latitude = None
    mock_detection_with_ioc_3.detection.longitude = None
    mock_detection_with_ioc_3.detection.species_confidence_threshold = 0.03
    mock_detection_with_ioc_3.detection.week = 1
    mock_detection_with_ioc_3.detection.sensitivity_setting = 1.25
    mock_detection_with_ioc_3.detection.overlap = 0.0
    mock_detection_with_ioc_3.ioc_english_name = "Northern Cardinal"
    mock_detection_with_ioc_3.translated_name = "Northern Cardinal"
    mock_detection_with_ioc_3.family = "Cardinalidae"
    mock_detection_with_ioc_3.genus = "Cardinalis"
    mock_detection_with_ioc_3.order_name = "Passeriformes"

    # Mock the IOC service method to return our mock DetectionWithIOCData objects
    detection_manager.detection_query_service.get_detections_with_ioc_data.return_value = [
        mock_detection_with_ioc_1,
        mock_detection_with_ioc_2,
        mock_detection_with_ioc_3,
    ]

    # Mock the fallback get_all_detections in case IOC fails
    mock_detections = [
        Detection(
            id=1,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name_tensor="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 0, 0),
            confidence=0.9,
            audio_file_id=101,  # Assign a mock audio_file_id
        ),
        Detection(
            id=2,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name_tensor="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 15, 0),
            confidence=0.8,
            audio_file_id=102,  # Assign a mock audio_file_id
        ),
        Detection(
            id=3,
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name_tensor="Northern Cardinal",
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
    assert "American Robin" in df["common_name"].unique()
    assert "Northern Cardinal" in df["common_name"].unique()


def test_get_best_detections(reporting_manager, detection_manager):
    """Should return a list of best detections sorted by confidence."""
    detection_manager.get_best_detections.return_value = [
        {"common_name": "Northern Cardinal", "confidence": 0.95},
        {"common_name": "American Robin", "confidence": 0.9},
    ]

    best_detections = reporting_manager.get_best_detections(limit=2)

    assert len(best_detections) == 2
    assert best_detections[0]["common_name"] == "Northern Cardinal"
    assert best_detections[0]["confidence"] == 0.95
    detection_manager.get_best_detections.assert_called_once_with(2)


def test_get_data__empty_detections(reporting_manager, detection_manager):
    """Should handle empty detections and return empty DataFrame with correct columns."""
    # Mock empty detections
    detection_manager.get_all_detections.return_value = []

    # Call get_data
    df = reporting_manager.get_data()

    # Verify DataFrame is empty but has correct structure
    assert df.empty
    assert list(df.columns) == [
        "common_name",
        "date",
        "time",
        "scientific_name",
        "confidence",
        "latitude",
        "longitude",
        "species_confidence_threshold",
        "week",
        "sensitivity_setting",
        "overlap",
    ]
    assert df.index.name == "datetime"
    assert pd.api.types.is_datetime64_any_dtype(df.index)


def test_get_todays_detections(reporting_manager, detection_manager_no_ioc):
    """Should retrieve detections for the current day."""
    # Replace the detection_manager in the reporting_manager with non-IOC version
    reporting_manager.detection_manager = detection_manager_no_ioc
    
    today = datetime.date(2025, 7, 15)

    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        # Create mock Detection objects
        import uuid
        from birdnetpi.models.database_models import Detection

        mock_detections = [
            Detection(
                id=uuid.uuid4(),
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name_tensor="American Robin",
                timestamp=datetime.datetime(2025, 7, 15, 10, 0, 0),
                confidence=0.9,
                audio_file_id=uuid.uuid4(),
            ),
            Detection(
                id=uuid.uuid4(),
                species_tensor="Cardinalis cardinalis_Northern Cardinal",
                scientific_name="Cardinalis cardinalis",
                common_name_tensor="Northern Cardinal",
                timestamp=datetime.datetime(2025, 7, 15, 14, 30, 0),
                confidence=0.95,
                audio_file_id=uuid.uuid4(),
            ),
            # Add a detection from a different day that should be filtered out
            Detection(
                id=uuid.uuid4(),
                species_tensor="Cyanocitta cristata_Blue Jay",
                scientific_name="Cyanocitta cristata",
                common_name_tensor="Blue Jay",
                timestamp=datetime.datetime(2025, 7, 14, 12, 0, 0),  # Different day
                confidence=0.85,
                audio_file_id=uuid.uuid4(),
            ),
        ]

        detection_manager_no_ioc.get_all_detections.return_value = mock_detections

        # Call the method
        todays_detections = reporting_manager.get_todays_detections()

        # Verify the results - only 2 detections from today
        assert len(todays_detections) == 2
        assert todays_detections[0]["common_name"] == "American Robin"
        assert todays_detections[1]["common_name"] == "Northern Cardinal"
        assert todays_detections[0]["date"] == "2025-07-15"
        assert todays_detections[0]["time"] == "10:00:00"
        assert todays_detections[0]["confidence"] == 0.9

        # Verify the detection manager was called
        detection_manager_no_ioc.get_all_detections.assert_called_once()


def test_date_filter(reporting_manager):
    """Should filter DataFrame by date range."""
    # Create test DataFrame with datetime index
    dates = pd.date_range(start="2025-07-10", end="2025-07-20", freq="D")
    df = pd.DataFrame({"value": range(len(dates))}, index=dates)

    # Filter from 2025-07-12 to 2025-07-15
    filtered_df = reporting_manager.date_filter(df, "2025-07-12", "2025-07-15")

    # Verify the filtered DataFrame contains the expected dates
    # The implementation adds 1 day to end_date, so it will include 2025-07-16
    expected_dates = pd.date_range(start="2025-07-12", end="2025-07-16", freq="D")
    assert len(filtered_df) == len(expected_dates)
    assert all(date in filtered_df.index for date in expected_dates)

    # Test edge case with single row result (should return DataFrame not Series)
    filtered_single = reporting_manager.date_filter(df, "2025-07-15", "2025-07-15")
    assert isinstance(filtered_single, pd.DataFrame)
    assert len(filtered_single) == 2  # 07-15 and 07-16 due to +1 day
