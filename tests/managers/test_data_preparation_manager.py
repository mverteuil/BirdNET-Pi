import datetime

import pandas as pd
import pytest

from birdnetpi.managers.data_preparation_manager import DataPreparationManager


@pytest.fixture
def data_preparation_manager():
    """Provide a DataPreparationManager instance for testing."""
    return DataPreparationManager()


@pytest.fixture
def sample_dataframe():
    """Provide a sample DataFrame for testing data preparation methods."""
    data = {
        "com_name": [
            "Common Blackbird",
            "Eurasian Robin",
            "Common Blackbird",
            "Eurasian Robin",
            "House Sparrow",
        ],
        "DateTime": [
            datetime.datetime(2023, 1, 1, 8, 0, 0),
            datetime.datetime(2023, 1, 1, 9, 0, 0),
            datetime.datetime(2023, 1, 1, 10, 0, 0),
            datetime.datetime(2023, 1, 2, 8, 0, 0),
            datetime.datetime(2023, 1, 2, 9, 0, 0),
        ],
    }
    df = pd.DataFrame(data)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df = df.set_index("DateTime")
    return df


def test_hms_to_dec_should_convert_time_to_decimal_hours():
    """Should correctly convert a datetime.time object to decimal hours."""
    time_obj = datetime.time(1, 30, 0)  # 1 hour, 30 minutes, 0 seconds
    expected_decimal_hours = 1.5
    assert DataPreparationManager.hms_to_dec(time_obj) == expected_decimal_hours


def test_hms_to_str_should_format_time_to_hh_mm_string():
    """Should correctly format a datetime.time object to HH:MM string."""
    time_obj = datetime.time(9, 5, 30)  # 09:05:30
    expected_time_string = "09:05"
    assert DataPreparationManager.hms_to_str(time_obj) == expected_time_string


def test_get_species_counts_should_return_correct_counts(
    data_preparation_manager, sample_dataframe
):
    """Should return correct counts of each common name in the DataFrame."""
    species_counts = data_preparation_manager.get_species_counts(sample_dataframe)
    assert species_counts["Common Blackbird"] == 2
    assert species_counts["Eurasian Robin"] == 2
    assert species_counts["House Sparrow"] == 1


def test_get_hourly_crosstab_should_generate_correct_crosstab(
    data_preparation_manager, sample_dataframe
):
    """Should generate a correct crosstabulation of common names by hour."""
    hourly_crosstab = data_preparation_manager.get_hourly_crosstab(sample_dataframe)
    assert hourly_crosstab.loc["Common Blackbird", 8] == 1
    assert hourly_crosstab.loc["Eurasian Robin", 9] == 1
    assert hourly_crosstab.loc["All", 10] == 1
    assert hourly_crosstab.loc["All", "All"] == 5


def test_get_daily_crosstab_should_generate_correct_crosstab(
    data_preparation_manager, sample_dataframe
):
    """Should generate a correct crosstabulation of common names by date."""
    daily_crosstab = data_preparation_manager.get_daily_crosstab(sample_dataframe)
    assert daily_crosstab.loc["Common Blackbird", datetime.date(2023, 1, 1)] == 2
    assert daily_crosstab.loc["Eurasian Robin", datetime.date(2023, 1, 2)] == 1
    assert daily_crosstab.loc["All", datetime.date(2023, 1, 1)] == 3
    assert daily_crosstab.loc["All", "All"] == 5


def test_time_resample_should_resample_dataframe_correctly(
    data_preparation_manager, sample_dataframe
):
    """Should resample the DataFrame based on the given time interval."""
    resampled_df = data_preparation_manager.time_resample(sample_dataframe, "h")
    assert len(resampled_df) == 26
    assert resampled_df.iloc[0]["com_name"] == "Common Blackbird"


def test_time_resample_should_handle_raw_resample(
    data_preparation_manager, sample_dataframe
):
    """Should handle 'Raw' resample option by returning the 'com_name' series."""
    resampled_df = data_preparation_manager.time_resample(sample_dataframe, "Raw")
    assert isinstance(resampled_df, pd.DataFrame)
    assert resampled_df.iloc[0]["com_name"] == "Common Blackbird"
