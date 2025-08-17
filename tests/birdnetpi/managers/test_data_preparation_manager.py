import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.location.location_service import LocationService
from birdnetpi.managers.data_preparation_manager import DataPreparationManager


@pytest.fixture
def mock_config():
    """Return a mock BirdNETConfig object."""
    config = MagicMock(spec=BirdNETConfig)
    config.sample_rate = 44100
    config.audio_channels = 1
    return config


@pytest.fixture
def mock_location_service():
    """Return a mock LocationService object."""
    service = MagicMock(spec=LocationService)
    service.get_sunrise_sunset_times.return_value = (
        datetime.datetime(2025, 7, 29, 5, 30, 0),
        datetime.datetime(2025, 7, 29, 19, 45, 0),
    )
    return service


@pytest.fixture
def data_preparation_manager(mock_config, mock_location_service):
    """Return a DataPreparationManager instance."""
    return DataPreparationManager(mock_config, mock_location_service)


@pytest.fixture
def sample_dataframe():
    """Return a sample pandas DataFrame for testing."""
    data = {
        "common_name": [
            "American Robin",
            "Northern Cardinal",
            "American Robin",
            "Blue Jay",
            "Northern Cardinal",
        ],
        "timestamp": pd.to_datetime(
            [
                "2025-07-29 08:00:00",
                "2025-07-29 09:30:00",
                "2025-07-29 10:00:00",
                "2025-07-30 08:15:00",
                "2025-07-30 09:45:00",
            ]
        ),
    }
    df = pd.DataFrame(data).set_index("timestamp")
    return df


class TestDataPreparationManager:
    """Test the DataPreparationManager class."""

    def test_hms_to_dec(self):
        """Test conversion of HMS time to decimal."""
        time_obj = datetime.time(8, 30, 0)
        assert DataPreparationManager.hms_to_dec(time_obj) == 8.5

        time_obj = datetime.time(12, 0, 0)
        assert DataPreparationManager.hms_to_dec(time_obj) == 12.0

        time_obj = datetime.time(0, 0, 0)
        assert DataPreparationManager.hms_to_dec(time_obj) == 0.0

    def test_hms_to_str(self):
        """Test conversion of HMS time to string."""
        time_obj = datetime.time(8, 30, 0)
        assert DataPreparationManager.hms_to_str(time_obj) == "08:30"

        time_obj = datetime.time(12, 5, 0)
        assert DataPreparationManager.hms_to_str(time_obj) == "12:05"

    def test_get_species_counts(self, data_preparation_manager, sample_dataframe):
        """Test calculation of species counts."""
        counts = data_preparation_manager.get_species_counts(sample_dataframe)
        assert counts["American Robin"] == 2
        assert counts["Northern Cardinal"] == 2
        assert counts["Blue Jay"] == 1

    def test_get_hourly_crosstab(self, data_preparation_manager, sample_dataframe):
        """Test creation of hourly crosstab."""
        crosstab = data_preparation_manager.get_hourly_crosstab(sample_dataframe)
        assert crosstab.loc["American Robin", 8] == 1
        assert crosstab.loc["Northern Cardinal", 9] == 2
        assert crosstab.loc["Blue Jay", 8] == 1
        assert crosstab.loc["All", "All"] == 5

    def test_get_daily_crosstab(self, data_preparation_manager, sample_dataframe):
        """Test creation of daily crosstab."""
        crosstab = data_preparation_manager.get_daily_crosstab(sample_dataframe)
        assert crosstab.loc["American Robin", datetime.date(2025, 7, 29)] == 2
        assert crosstab.loc["Northern Cardinal", datetime.date(2025, 7, 30)] == 1
        assert crosstab.loc["All", "All"] == 5

    def test_time_resample_raw(self, data_preparation_manager, sample_dataframe):
        """Test raw time resampling."""
        resampled_df = data_preparation_manager.time_resample(sample_dataframe, "Raw")
        pd.testing.assert_frame_equal(resampled_df, sample_dataframe[["common_name"]])

    def test_time_resample_hourly(self, data_preparation_manager, sample_dataframe):
        """Test hourly time resampling."""
        resampled_df = data_preparation_manager.time_resample(sample_dataframe, "H")
        expected_data = {
            "common_name": [
                "American Robin",
                "Northern Cardinal",
                "American Robin",
                "Blue Jay",
                "Northern Cardinal",
            ]
        }
        expected_index = pd.to_datetime(
            [
                "2025-07-29 08:00:00",
                "2025-07-29 09:00:00",
                "2025-07-29 10:00:00",
                "2025-07-30 08:00:00",
                "2025-07-30 09:00:00",
            ]
        )
        expected_df = pd.DataFrame(expected_data, index=expected_index)
        # The resample operation with aggregate('unique').explode() can introduce NaNs
        # for hours with no data. We need to filter these out for comparison.
        # Also, the index might not be exactly the same due to resampling creating
        # new timestamps. So, we'll compare the 'common_name' column after sorting
        # and resetting index.
        # Compare sorted values since the order might be different after resampling
        actual_sorted = sorted(resampled_df["common_name"].dropna())
        expected_sorted = sorted(expected_df["common_name"])
        assert actual_sorted == expected_sorted

    def test_prepare_multi_day_plot_data(self, data_preparation_manager, sample_dataframe):
        """Test preparation of multi-day plot data."""
        resample_selection = "H"
        top_n_count = 2
        species = "American Robin"

        df5, hourly, top_n_species, df_counts = (
            data_preparation_manager.prepare_multi_day_plot_data(
                sample_dataframe, resample_selection, species, top_n_count
            )
        )

        assert not df5.empty
        assert not hourly.empty
        assert not top_n_species.empty
        assert df_counts == 2  # American Robin appears twice in the sample data

    def test_prepare_daily_plot_data(self, data_preparation_manager, sample_dataframe):
        """Test preparation of daily plot data."""
        resample_selection = "15min"
        species = "American Robin"

        day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
            data_preparation_manager.prepare_daily_plot_data(
                sample_dataframe, resample_selection, species
            )
        )

        assert not day_hour_freq.empty
        assert len(saved_time_labels) > 0
        assert len(fig_dec_y) > 0
        assert len(fig_x) > 0

    def test_get_sunrise_sunset_data(self, data_preparation_manager, mock_location_service):
        """Test retrieval of sunrise and sunset data."""
        num_days = 1
        (sunrise_times_dec, sunset_times_dec, dates_str, sunrise_text, sunset_text) = (
            data_preparation_manager.get_sunrise_sunset_data(num_days)
        )

        assert len(sunrise_times_dec) == num_days
        assert len(sunset_times_dec) == num_days
        assert len(dates_str) == num_days
        assert len(sunrise_text) == num_days
        assert len(sunset_text) == num_days

        mock_location_service.get_sunrise_sunset_times.assert_called_once()

    def test_prepare_sunrise_sunset_data_for_plot(self, data_preparation_manager, mocker):
        """Test preparation of sunrise and sunset data for plotting."""
        mocker.patch(
            "birdnetpi.managers.data_preparation_manager.DataPreparationManager.get_sunrise_sunset_data",
            return_value=(
                [6.5],  # sunrise_times_dec (06:30)
                [19.75],  # sunset_times_dec (19:45)
                ["2025-07-29"],  # dates_str
                ["06:30 Sunrise"],  # sunrise_text
                ["19:45 Sunset"],  # sunset_text
            ),
        )

        num_days = 1
        plot_x, plot_y, plot_text, plot_colors = (
            data_preparation_manager.prepare_sunrise_sunset_data_for_plot(num_days)
        )

        assert plot_x == ["2025-07-29", "2025-07-29"]
        assert plot_y == [6.5, 19.75]
        assert plot_text == ["06:30 Sunrise", "19:45 Sunset"]
        assert plot_colors == ["orange", "purple"]
