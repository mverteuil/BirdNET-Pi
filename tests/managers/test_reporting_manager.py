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
    mock.language = "en"
    mock.timezone = "UTC"
    mock.apprise_only_notify_species_names = ""
    mock.database = MagicMock(path="/tmp/test.db")  # Mock database path
    return mock


@pytest.fixture
def mock_location_service():
    """Provide a mock LocationService instance."""
    return Mock(spec=LocationService)


@pytest.fixture
def reporting_manager(
    detection_manager,
    path_resolver,
    mock_plotting_manager,
    mock_data_preparation_manager,
    mock_config,  # Added mock_config
    mock_location_service,  # Added mock_location_service
):
    """Provide a ReportingManager instance with mocked dependencies."""
    manager = ReportingManager(
        detection_manager=detection_manager,
        path_resolver=path_resolver,
        config=mock_config,
        plotting_manager=mock_plotting_manager,
        data_preparation_manager=mock_data_preparation_manager,
        location_service=mock_location_service,
    )
    return manager


def test_get_most_recent_detections(reporting_manager, detection_manager):
    """Should return a list of recent detections."""
    detection_manager.get_most_recent_detections_with_localization.return_value = [
        {"common_name": "American Robin", "date": "2025-07-12", "time": "10:00:00"},
        {"common_name": "Northern Cardinal", "date": "2025-07-12", "time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["common_name"] == "American Robin"
    detection_manager.get_most_recent_detections_with_localization.assert_called_once_with(2, "en")


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
    # Mock DetectionWithLocalization objects for the IOC service
    from unittest.mock import MagicMock

    mock_detection_with_l10n_1 = MagicMock()
    mock_detection_with_l10n_1.get_best_common_name.return_value = "American Robin"
    mock_detection_with_l10n_1.timestamp = datetime.datetime(2025, 7, 15, 8, 0, 0)
    mock_detection_with_l10n_1.scientific_name = "Turdus migratorius"
    mock_detection_with_l10n_1.confidence = 0.9
    mock_detection_with_l10n_1.detection.latitude = None
    mock_detection_with_l10n_1.detection.longitude = None
    mock_detection_with_l10n_1.detection.species_confidence_threshold = 0.03
    mock_detection_with_l10n_1.detection.week = 1
    mock_detection_with_l10n_1.detection.sensitivity_setting = 1.25
    mock_detection_with_l10n_1.detection.overlap = 0.0
    mock_detection_with_l10n_1.ioc_english_name = "American Robin"
    mock_detection_with_l10n_1.translated_name = "American Robin"
    mock_detection_with_l10n_1.family = "Turdidae"
    mock_detection_with_l10n_1.genus = "Turdus"
    mock_detection_with_l10n_1.order_name = "Passeriformes"

    mock_detection_with_l10n_2 = MagicMock()
    mock_detection_with_l10n_2.get_best_common_name.return_value = "American Robin"
    mock_detection_with_l10n_2.timestamp = datetime.datetime(2025, 7, 15, 8, 15, 0)
    mock_detection_with_l10n_2.scientific_name = "Turdus migratorius"
    mock_detection_with_l10n_2.confidence = 0.8
    mock_detection_with_l10n_2.detection.latitude = None
    mock_detection_with_l10n_2.detection.longitude = None
    mock_detection_with_l10n_2.detection.species_confidence_threshold = 0.03
    mock_detection_with_l10n_2.detection.week = 1
    mock_detection_with_l10n_2.detection.sensitivity_setting = 1.25
    mock_detection_with_l10n_2.detection.overlap = 0.0
    mock_detection_with_l10n_2.ioc_english_name = "American Robin"
    mock_detection_with_l10n_2.translated_name = "American Robin"
    mock_detection_with_l10n_2.family = "Turdidae"
    mock_detection_with_l10n_2.genus = "Turdus"
    mock_detection_with_l10n_2.order_name = "Passeriformes"

    mock_detection_with_l10n_3 = MagicMock()
    mock_detection_with_l10n_3.get_best_common_name.return_value = "Northern Cardinal"
    mock_detection_with_l10n_3.timestamp = datetime.datetime(2025, 7, 15, 9, 0, 0)
    mock_detection_with_l10n_3.scientific_name = "Cardinalis cardinalis"
    mock_detection_with_l10n_3.confidence = 0.95
    mock_detection_with_l10n_3.detection.latitude = None
    mock_detection_with_l10n_3.detection.longitude = None
    mock_detection_with_l10n_3.detection.species_confidence_threshold = 0.03
    mock_detection_with_l10n_3.detection.week = 1
    mock_detection_with_l10n_3.detection.sensitivity_setting = 1.25
    mock_detection_with_l10n_3.detection.overlap = 0.0
    mock_detection_with_l10n_3.ioc_english_name = "Northern Cardinal"
    mock_detection_with_l10n_3.translated_name = "Northern Cardinal"
    mock_detection_with_l10n_3.family = "Cardinalidae"
    mock_detection_with_l10n_3.genus = "Cardinalis"
    mock_detection_with_l10n_3.order_name = "Passeriformes"

    # Mock the localization service method to return our mock DetectionWithLocalization objects
    detection_manager.detection_query_service.get_detections_with_localization.return_value = [
        mock_detection_with_l10n_1,
        mock_detection_with_l10n_2,
        mock_detection_with_l10n_3,
    ]

    # Mock the fallback get_all_detections in case IOC fails
    mock_detections = [
        Detection(
            id=1,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 0, 0),
            confidence=0.9,
            audio_file_id=101,  # Assign a mock audio_file_id
        ),
        Detection(
            id=2,
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 15, 0),
            confidence=0.8,
            audio_file_id=102,  # Assign a mock audio_file_id
        ),
        Detection(
            id=3,
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
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
            df, resample_selection="15min", species="American Robin"
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
                common_name="American Robin",
                timestamp=datetime.datetime(2025, 7, 15, 10, 0, 0),
                confidence=0.9,
                audio_file_id=uuid.uuid4(),
            ),
            Detection(
                id=uuid.uuid4(),
                species_tensor="Cardinalis cardinalis_Northern Cardinal",
                scientific_name="Cardinalis cardinalis",
                common_name="Northern Cardinal",
                timestamp=datetime.datetime(2025, 7, 15, 14, 30, 0),
                confidence=0.95,
                audio_file_id=uuid.uuid4(),
            ),
            # Add a detection from a different day that should be filtered out
            Detection(
                id=uuid.uuid4(),
                species_tensor="Cyanocitta cristata_Blue Jay",
                scientific_name="Cyanocitta cristata",
                common_name="Blue Jay",
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


# COMPREHENSIVE WEEKLY REPORT TESTS


def test_get_weekly_report_data__no_detections(reporting_manager, detection_manager):
    """Should handle scenario with no detections at all."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        # Mock empty detections
        detection_manager.get_all_detections.return_value = []
        detection_manager.get_detection_counts_by_date_range.return_value = None
        detection_manager.get_top_species_with_prior_counts.return_value = []
        detection_manager.get_new_species_data.return_value = []

        report_data = reporting_manager.get_weekly_report_data()

        assert report_data["total_detections_current"] == 0
        assert report_data["unique_species_current"] == 0
        assert report_data["total_detections_prior"] == 0
        assert report_data["unique_species_prior"] == 0
        assert report_data["percentage_diff_total"] == 0
        assert report_data["percentage_diff_unique_species"] == 0
        assert report_data["top_10_species"] == []
        assert report_data["new_species"] == []


def test_get_weekly_report_data__with_data_latest_date_calculation(
    reporting_manager, detection_manager
):
    """Should calculate date ranges based on latest available data."""
    today = datetime.date(2025, 8, 15)  # Friday

    # Create mock detections with latest date being 2025-08-10 (Sunday)
    mock_detection = MagicMock()
    mock_detection.timestamp = datetime.datetime(2025, 8, 10, 14, 30, 0)
    detection_manager.get_all_detections.return_value = [mock_detection]

    detection_manager.get_detection_counts_by_date_range.side_effect = [
        {"total_count": 50, "unique_species": 8},  # Current week
        {"total_count": 30, "unique_species": 5},  # Prior week
    ]
    detection_manager.get_top_species_with_prior_counts.return_value = []
    detection_manager.get_new_species_data.return_value = []

    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        report_data = reporting_manager.get_weekly_report_data()

        # Should use Aug 4-10 as the week (Sunday = Aug 10)
        assert report_data["start_date"] == "2025-08-04"
        assert report_data["end_date"] == "2025-08-10"
        assert report_data["week_number"] == 32


def test_get_weekly_report_data__latest_date_is_sunday(reporting_manager, detection_manager):
    """Should handle when latest detection date is already a Sunday."""
    today = datetime.date(2025, 8, 15)  # Friday

    # Create mock detections with latest date being Sunday
    mock_detection = MagicMock()
    mock_detection.timestamp = datetime.datetime(2025, 8, 11, 10, 0, 0)  # Sunday
    detection_manager.get_all_detections.return_value = [mock_detection]

    detection_manager.get_detection_counts_by_date_range.side_effect = [
        {"total_count": 25, "unique_species": 6},  # Current week
        {"total_count": 20, "unique_species": 4},  # Prior week
    ]
    detection_manager.get_top_species_with_prior_counts.return_value = []
    detection_manager.get_new_species_data.return_value = []

    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        report_data = reporting_manager.get_weekly_report_data()

        # Should use Aug 5-11 as the week (Sunday = Aug 11)
        assert report_data["start_date"] == "2025-08-05"
        assert report_data["end_date"] == "2025-08-11"
        assert report_data["week_number"] == 32


def test_get_weekly_report_data__invalid_timestamps(reporting_manager, detection_manager):
    """Should handle detections with invalid or None timestamps."""
    today = datetime.date(2025, 7, 12)  # Saturday

    # Create mock detections with invalid timestamps
    mock_detection_valid = MagicMock()
    mock_detection_valid.timestamp = datetime.datetime(2025, 7, 10, 12, 0, 0)

    mock_detection_none = MagicMock()
    mock_detection_none.timestamp = None

    mock_detection_string = MagicMock()
    mock_detection_string.timestamp = "invalid"

    detection_manager.get_all_detections.return_value = [
        mock_detection_valid,
        mock_detection_none,
        mock_detection_string,
    ]

    detection_manager.get_detection_counts_by_date_range.side_effect = [
        {"total_count": 10, "unique_species": 3},
        {"total_count": 5, "unique_species": 2},
    ]
    detection_manager.get_top_species_with_prior_counts.return_value = []
    detection_manager.get_new_species_data.return_value = []

    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        # Should not raise an exception and use the valid timestamp
        report_data = reporting_manager.get_weekly_report_data()

        assert report_data["start_date"] == "2025-07-01"  # Based on July 10 detection
        assert report_data["end_date"] == "2025-07-07"  # Monday of week containing July 10


def test_calculate_percentage_differences__zero_prior(reporting_manager):
    """Should handle zero prior values in percentage calculations."""
    result_total, result_unique = reporting_manager._calculate_percentage_differences(10, 5, 0, 0)

    assert result_total == 0  # Should be 0 when prior is 0
    assert result_unique == 0  # Should be 0 when prior is 0


def test_calculate_percentage_differences__normal_calculation(reporting_manager):
    """Should calculate percentage differences correctly for normal values."""
    result_total, result_unique = reporting_manager._calculate_percentage_differences(
        120, 15, 100, 10
    )

    assert result_total == 20  # (120-100)/100 * 100 = 20%
    assert result_unique == 50  # (15-10)/10 * 100 = 50%


def test_calculate_percentage_differences__negative_change(reporting_manager):
    """Should calculate negative percentage differences correctly."""
    result_total, result_unique = reporting_manager._calculate_percentage_differences(
        80, 6, 100, 10
    )

    assert result_total == -20  # (80-100)/100 * 100 = -20%
    assert result_unique == -40  # (6-10)/10 * 100 = -40%


def test_calculate_percentage_differences__fractional_rounding(reporting_manager):
    """Should round percentage differences to nearest integer."""
    result_total, result_unique = reporting_manager._calculate_percentage_differences(
        103, 11, 100, 10
    )

    assert result_total == 3  # 3% exact
    assert result_unique == 10  # 10% exact

    # Test rounding behavior
    result_total_rounded, _ = reporting_manager._calculate_percentage_differences(101, 10, 100, 10)

    assert result_total_rounded == 1  # 1% exact


def test_get_top_species_data__no_data(reporting_manager, detection_manager):
    """Should handle empty top species data."""
    detection_manager.get_top_species_with_prior_counts.return_value = []

    result = reporting_manager._get_top_species_data(
        datetime.date(2025, 7, 7),
        datetime.date(2025, 7, 13),
        datetime.date(2025, 6, 30),
        datetime.date(2025, 7, 6),
    )

    assert result == []


def test_get_top_species_data__with_zero_prior_counts(reporting_manager, detection_manager):
    """Should handle top species with zero prior counts (new species in top 10)."""
    detection_manager.get_top_species_with_prior_counts.return_value = [
        {
            "scientific_name": "Turdus migratorius",
            "common_name": "American Robin",
            "current_count": 25,
            "prior_count": 0,  # New in top 10
        },
        {
            "scientific_name": "Cardinalis cardinalis",
            "common_name": "Northern Cardinal",
            "current_count": 20,
            "prior_count": 15,
        },
    ]

    result = reporting_manager._get_top_species_data(
        datetime.date(2025, 7, 7),
        datetime.date(2025, 7, 13),
        datetime.date(2025, 6, 30),
        datetime.date(2025, 7, 6),
    )

    assert len(result) == 2
    assert result[0]["common_name"] == "American Robin"
    assert result[0]["count"] == 25
    assert result[0]["percentage_diff"] == 0  # Should be 0 when prior_count is 0

    assert result[1]["common_name"] == "Northern Cardinal"
    assert result[1]["count"] == 20
    assert result[1]["percentage_diff"] == 33  # (20-15)/15 * 100 = 33.33 -> 33


def test_get_new_species_data__no_data(reporting_manager, detection_manager):
    """Should handle empty new species data."""
    detection_manager.get_new_species_data.return_value = []

    result = reporting_manager._get_new_species_data(
        datetime.date(2025, 7, 7),
        datetime.date(2025, 7, 13),
    )

    assert result == []


def test_get_new_species_data__with_data(reporting_manager, detection_manager):
    """Should format new species data correctly."""
    detection_manager.get_new_species_data.return_value = [
        {"species": "Blue Jay", "count": 8},
        {"species": "House Sparrow", "count": 12},
    ]

    result = reporting_manager._get_new_species_data(
        datetime.date(2025, 7, 7),
        datetime.date(2025, 7, 13),
    )

    assert len(result) == 2
    assert result[0]["common_name"] == "Blue Jay"
    assert result[0]["count"] == 8
    assert result[1]["common_name"] == "House Sparrow"
    assert result[1]["count"] == 12


def test_get_weekly_stats__none_results(reporting_manager, detection_manager):
    """Should handle None results from detection counts."""
    detection_manager.get_detection_counts_by_date_range.side_effect = [None, None]

    current_stats, prior_stats = reporting_manager._get_weekly_stats(
        datetime.date(2025, 7, 7),
        datetime.date(2025, 7, 13),
        datetime.date(2025, 6, 30),
        datetime.date(2025, 7, 6),
    )

    assert current_stats is None
    assert prior_stats is None


def test_get_weekly_report_data__week_boundary_edge_cases(reporting_manager, detection_manager):
    """Should handle various week boundary scenarios correctly."""
    # Test different weekdays as latest date
    test_cases = [
        (datetime.date(2025, 7, 7), "2025-07-01", "2025-07-07"),  # Monday -> week ending Monday
        (datetime.date(2025, 7, 12), "2025-07-01", "2025-07-07"),  # Saturday -> week ending Monday
        (datetime.date(2025, 7, 13), "2025-07-07", "2025-07-13"),  # Sunday -> week ending Sunday
    ]

    for latest_date, expected_start, expected_end in test_cases:
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime.combine(latest_date, datetime.time(12, 0, 0))
        detection_manager.get_all_detections.return_value = [mock_detection]

        detection_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 10, "unique_species": 5},
            {"total_count": 8, "unique_species": 4},
        ]
        detection_manager.get_top_species_with_prior_counts.return_value = []
        detection_manager.get_new_species_data.return_value = []

        with patch(
            "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
        ) as mock_date:
            mock_date.today.return_value = datetime.date(2025, 7, 15)

            report_data = reporting_manager.get_weekly_report_data()

            assert report_data["start_date"] == expected_start, f"Failed for {latest_date}"
            assert report_data["end_date"] == expected_end, f"Failed for {latest_date}"


def test_get_weekly_report_data__large_numbers(reporting_manager, detection_manager):
    """Should handle large detection counts without overflow."""
    today = datetime.date(2025, 7, 12)
    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        detection_manager.get_all_detections.return_value = []
        detection_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 50000, "unique_species": 500},  # Large current week
            {"total_count": 25000, "unique_species": 250},  # Large prior week
        ]
        detection_manager.get_top_species_with_prior_counts.return_value = []
        detection_manager.get_new_species_data.return_value = []

        report_data = reporting_manager.get_weekly_report_data()

        assert report_data["total_detections_current"] == 50000
        assert report_data["unique_species_current"] == 500
        assert report_data["percentage_diff_total"] == 100  # 100% increase
        assert report_data["percentage_diff_unique_species"] == 100  # 100% increase


def test_get_weekly_report_data__comprehensive_integration(reporting_manager, detection_manager):
    """Should integrate all components for a comprehensive weekly report."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch(
        "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        # Mock detection data with realistic timestamps
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        detection_manager.get_all_detections.return_value = [mock_detection]

        detection_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 156, "unique_species": 23},  # Current week stats
            {"total_count": 134, "unique_species": 19},  # Prior week stats
        ]

        detection_manager.get_top_species_with_prior_counts.return_value = [
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "current_count": 35,
                "prior_count": 28,
            },
            {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "current_count": 22,
                "prior_count": 18,
            },
            {
                "scientific_name": "Cyanocitta cristata",
                "common_name": "Blue Jay",
                "current_count": 18,
                "prior_count": 0,
            },  # New in top 10
        ]

        detection_manager.get_new_species_data.return_value = [
            {"species": "House Finch", "count": 7},
            {"species": "White-breasted Nuthatch", "count": 4},
        ]

        report_data = reporting_manager.get_weekly_report_data()

        # Verify all components are correctly integrated
        assert report_data["start_date"] == "2025-07-01"  # Week containing July 10
        assert report_data["end_date"] == "2025-07-07"  # Monday of week containing July 10
        assert report_data["week_number"] == 27
        assert report_data["total_detections_current"] == 156
        assert report_data["unique_species_current"] == 23
        assert report_data["total_detections_prior"] == 134
        assert report_data["unique_species_prior"] == 19
        assert report_data["percentage_diff_total"] == 16  # (156-134)/134 * 100
        assert report_data["percentage_diff_unique_species"] == 21  # (23-19)/19 * 100

        # Verify top species data
        assert len(report_data["top_10_species"]) == 3
        assert report_data["top_10_species"][0]["common_name"] == "American Robin"
        assert report_data["top_10_species"][0]["count"] == 35
        assert report_data["top_10_species"][0]["percentage_diff"] == 25  # (35-28)/28 * 100

        assert report_data["top_10_species"][2]["common_name"] == "Blue Jay"
        assert report_data["top_10_species"][2]["percentage_diff"] == 0  # New species

        # Verify new species data
        assert len(report_data["new_species"]) == 2
        assert report_data["new_species"][0]["common_name"] == "House Finch"
        assert report_data["new_species"][0]["count"] == 7
