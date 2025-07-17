import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.models.database_models import Detection
from birdnetpi.utils.config_file_parser import ConfigFileParser


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
def reporting_manager(
    detection_manager,
    file_path_resolver,
    mock_plotting_manager,
    mock_data_preparation_manager,
):
    """Provide a ReportingManager instance with mocked dependencies."""
    mock_config_parser = MagicMock(spec=ConfigFileParser)
    mock_config_parser.load_config.return_value = MagicMock(
        site_name="Test Site",
        latitude=0.0,
        longitude=0.0,
        model="test_model",
        sf_thresh=0.0,
        birdweather_id="test_id",
        apprise_input="test_input",
        apprise_notification_title="test_title",
        apprise_notification_body="test_body",
        apprise_notify_each_detection=False,
        apprise_notify_new_species=False,
        apprise_notify_new_species_each_day=False,
        apprise_weekly_report=False,
        minimum_time_limit=0,
        flickr_api_key="test_key",
        flickr_filter_email="test_email",
        database_lang="en",
        timezone="UTC",
        caddy_pwd="test_pwd",
        silence_update_indicator=False,
        birdnetpi_url="test_url",
        apprise_only_notify_species_names="",
        apprise_only_notify_species_names_2="",
        database=MagicMock(path=file_path_resolver.get_birds_db_path()),
    )
    manager = ReportingManager(
        detection_manager, file_path_resolver, mock_config_parser
    )
    manager.data_preparation_manager = mock_data_preparation_manager
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
                "com_name": "American Robin",
                "current_count": 20,
                "prior_count": 15,
            },
            {
                "com_name": "Northern Cardinal",
                "current_count": 15,
                "prior_count": 10,
            },
        ]

        detection_manager.get_new_species_data.return_value = [
            {"com_name": "Blue Jay", "count": 5}
        ]

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
            species="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 0, 0),
            confidence=0.9,
            audio_file_path="test1.wav",
        ),
        Detection(
            id=2,
            species="American Robin",
            timestamp=datetime.datetime(2025, 7, 15, 8, 15, 0),
            confidence=0.8,
            audio_file_path="test2.wav",
        ),
        Detection(
            id=3,
            species="Northern Cardinal",
            timestamp=datetime.datetime(2025, 7, 15, 9, 0, 0),
            confidence=0.95,
            audio_file_path="test3.wav",
        ),
    ]
    detection_manager.get_all_detections.return_value = mock_detections

    # Call get_data to get the DataFrame
    df = reporting_manager.get_data()

    # Call the method under test
    day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
        reporting_manager.get_daily_detection_data_for_plotting(
            df, resample_sel="15min", specie="American Robin"
        )
    )

    # Assertions
    assert isinstance(day_hour_freq, pd.DataFrame)
    assert "American Robin" in df["Com_Name"].unique()
    assert "Northern Cardinal" in df["Com_Name"].unique()

    # Check the shape and content of day_hour_freq
    # Expecting one row for the date and columns for the hours with detections
    assert day_hour_freq.shape == (1, 2)  # One day, two 15-min intervals
    assert day_hour_freq.loc[(datetime.date(2025, 7, 15),), datetime.time(8, 0, 0)] == 1
    assert (
        day_hour_freq.loc[(datetime.date(2025, 7, 15),), datetime.time(8, 15, 0)] == 1
    )

    # Check saved_time_labels
    assert saved_time_labels == ["08:00:00", "08:15:00"]

    # Check fig_dec_y
    assert fig_dec_y == [8.0, 8.25]

    # Check fig_x
    assert fig_x == ["15-07-2025"]

    # Test with a species that has no detections
    day_hour_freq_no_detection, _, _, _ = (
        reporting_manager.get_daily_detection_data_for_plotting(
            df, resample_sel="15min", specie="NonExistentBird"
        )
    )
    assert day_hour_freq_no_detection.empty
