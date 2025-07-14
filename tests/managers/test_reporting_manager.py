import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from managers.reporting_manager import ReportingManager


@pytest.fixture
def db_manager():
    """Provide a mock DatabaseManager instance."""
    return MagicMock()


@pytest.fixture
def reporting_manager(db_manager, file_path_resolver):
    """Provide a ReportingManager instance with mocked dependencies."""
    return ReportingManager(db_manager, file_path_resolver)


def test_get_most_recent_detections(reporting_manager, db_manager):
    """Should return a list of recent detections."""
    db_manager.get_most_recent_detections.return_value = [
        {"Com_Name": "American Robin", "Date": "2025-07-12", "Time": "10:00:00"},
        {"Com_Name": "Northern Cardinal", "Date": "2025-07-12", "Time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["Com_Name"] == "American Robin"
    db_manager.get_most_recent_detections.assert_called_once_with(2)


def test_get_weekly_report_data(reporting_manager, db_manager):
    """Should return a dictionary of weekly report data."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch("managers.reporting_manager.datetime.date") as mock_date:
        mock_date.today.return_value = today

        db_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 100, "unique_species": 10},  # Current week stats
            {"total_count": 80, "unique_species": 8},  # Prior week stats
        ]

        db_manager.get_top_species_with_prior_counts.return_value = [
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

        db_manager.get_new_species_data.return_value = [
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

        # Assertions for db_manager method calls
        db_manager.get_detection_counts_by_date_range.assert_any_call(
            datetime.date(2025, 6, 30), datetime.date(2025, 7, 6)
        )
        db_manager.get_detection_counts_by_date_range.assert_any_call(
            datetime.date(2025, 6, 23), datetime.date(2025, 6, 29)
        )
        db_manager.get_top_species_with_prior_counts.assert_called_once_with(
            datetime.date(2025, 6, 30),
            datetime.date(2025, 7, 6),
            datetime.date(2025, 6, 23),
            datetime.date(2025, 6, 29),
        )
        db_manager.get_new_species_data.assert_called_once_with(
            datetime.date(2025, 6, 30), datetime.date(2025, 7, 6)
        )


def test_generate_multi_day_species_and_hourly_plot(reporting_manager):
    """Should generate a multi-day species and hourly plot."""
    # Mock the DataFrame and internal methods
    mock_df = MagicMock()
    mock_df.__getitem__.return_value.resample.return_value.aggregate.return_value.explode.return_value = MagicMock(
        spec=pd.Series
    )
    mock_df.__getitem__.return_value.resample.return_value.count.return_value = (
        MagicMock(spec=pd.Series)
    )
    mock_df.index = MagicMock()
    mock_df.index.hour = MagicMock()
    mock_df.index.date = MagicMock()

    with patch.object(
        reporting_manager.data_preparation_manager,
        "time_resample",
        return_value=mock_df,
    ) as mock_time_resample:
        with patch.object(
            reporting_manager.data_preparation_manager,
            "get_hourly_crosstab",
            return_value=pd.DataFrame({"All": [100]}, index=["specie"]),
        ) as mock_get_hourly_crosstab:
            with patch.object(
                reporting_manager.data_preparation_manager,
                "get_species_counts",
                return_value=pd.Series([50, 30], index=["BirdA", "BirdB"]),
            ) as mock_get_species_counts:
                with patch.object(
                    reporting_manager.data_preparation_manager,
                    "get_daily_crosstab",
                    return_value=pd.DataFrame({"2025-07-10": [10]}, index=["specie"]),
                ) as mock_get_daily_crosstab:

                    result = (
                        reporting_manager.generate_multi_day_species_and_hourly_plot(
                            mock_df, "15min", "2025-07-10", "2025-07-12", 10, "specie"
                        )
                    )

        mock_time_resample.assert_called_once_with(mock_df, "15min")
        mock_get_hourly_crosstab.assert_called_once_with(mock_df)
        mock_get_species_counts.assert_called_once_with(mock_df)
        mock_get_daily_crosstab.assert_called_once_with(mock_df)
        assert isinstance(result, go.Figure)


def test_generate_daily_detections_plot(reporting_manager):
    """Should generate a daily detections plot."""
    mock_df = MagicMock()
    mock_df.__getitem__.return_value.resample.return_value.count.return_value = (
        MagicMock(spec=pd.Series)
    )
    mock_df.__getitem__.return_value.resample.return_value.count.return_value.index = (
        MagicMock()
    )
    mock_df.__getitem__.return_value.resample.return_value.count.return_value.index.date = MagicMock(
        return_value=[datetime.date(2025, 7, 10)]
    )
    mock_df.__getitem__.return_value.resample.return_value.count.return_value.index.time = MagicMock(
        return_value=[datetime.time(10, 0, 0)]
    )

    # Mock the day_hour_freq object that _prepare_daily_detection_data will return
    mock_day_hour_freq = MagicMock(spec=pd.DataFrame)
    mock_day_hour_freq.columns = [
        datetime.time(i, 0, 0) for i in range(24)
    ]  # Populate with mock time objects
    mock_day_hour_freq.index = MagicMock()
    mock_day_hour_freq.values.transpose.return_value = np.array(
        [[10] * 24]
    )  # Ensure it's a 2D array matching columns

    mock_saved_time_labels = [f"{i:02d}:00" for i in range(24)]
    mock_fig_dec_y = [float(i) for i in range(24)]
    mock_fig_x = ["10-07-2025"]

    # Mock the _prepare_daily_plot_data method
    with (
        patch.object(
            reporting_manager,
            "_prepare_daily_plot_data",
            return_value=(
                mock_day_hour_freq,
                mock_saved_time_labels,
                mock_fig_dec_y,
                mock_fig_x,
            ),
        ) as mock_prepare_data,
        patch.object(
            reporting_manager,
            "get_sunrise_sunset_data",
            return_value=([0], [0.5], ["Sunrise"]),
        ) as mock_get_sunrise_sunset_data,
        patch.object(
            reporting_manager.data_preparation_manager,
            "hms_to_str",
            return_value="08:00",
        ) as mock_hms_to_str,
        patch.object(
            reporting_manager.data_preparation_manager,
            "hms_to_dec",
            return_value=8.0,
        ) as mock_hms_to_dec,
    ):

        result = reporting_manager.generate_daily_detections_plot(
            mock_df, "15min", "2025-07-10", "specie", 7, "viridis"
        )

        mock_prepare_data.assert_called_once_with(mock_df, "15min", "specie")
        mock_get_sunrise_sunset_data.assert_called_once_with(7)
        mock_hms_to_str.assert_called()
        mock_hms_to_dec.assert_called()
        assert isinstance(result, go.Figure)
