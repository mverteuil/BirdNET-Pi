import datetime
from unittest.mock import Mock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.multi_day_plot_config import MultiDayPlotConfig
from birdnetpi.services.location_service import LocationService


@pytest.fixture
def mock_data_preparation_manager():
    """Provide a mock DataPreparationManager instance."""
    return Mock(spec=DataPreparationManager)


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    # Add any necessary attributes that PlottingManager might access from config
    return mock


@pytest.fixture
def mock_location_service():
    """Provide a mock LocationService instance."""
    return Mock(spec=LocationService)


@pytest.fixture
def plotting_manager():  # Removed mock_data_preparation_manager, mock_config, mock_location_service from arguments
    """Provide a PlottingManager instance with mocked dependencies."""
    with patch("birdnetpi.managers.plotting_manager.DataPreparationManager"):
        # Instantiate PlottingManager without passing these as arguments
        return PlottingManager()


@pytest.fixture
def sample_dataframe():
    """Provide a sample DataFrame for testing plotting methods."""
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


def test_add_polar_trace_to_figure_should_return_figure(plotting_manager):
    """Should return a plotly figure after adding a polar trace."""
    fig = go.Figure()
    hourly_df = pd.DataFrame({"All": [1, 2, 3]}, index=[0, 1, 2])
    species = "Common Blackbird"
    result_fig = plotting_manager._add_polar_trace_to_figure(fig, hourly_df, species)
    assert isinstance(result_fig, go.Figure)


def test_create_multi_day_plot_figure_should_return_figure(
    plotting_manager, mock_data_preparation_manager
):
    """Should return a plotly figure for multi-day plots."""
    df_counts = 10
    top_n = 5
    start_date = "2023-01-01"
    end_date = "23-01-07"
    resample_sel = "D"
    top_n_species = pd.Series([5, 3], index=["SpeciesA", "SpeciesB"])
    hourly = pd.DataFrame({"All": [1, 2, 3]}, index=[0, 1, 2])
    species = "SpeciesA"
    df5 = pd.DataFrame(
        {
            "com_name": ["SpeciesA", "SpeciesB"],
            "DateTime": [datetime.datetime(2023, 1, 1), datetime.datetime(2023, 1, 2)],
        }
    ).set_index("DateTime")

    # Mock the delegated calls
    mock_data_preparation_manager.get_daily_crosstab.return_value = pd.DataFrame(
        {"col1": [1, 2]}, index=["SpeciesA", "SpeciesB"]
    )
    plotting_manager.data_preparation_manager = mock_data_preparation_manager

    fig = plotting_manager._create_multi_day_plot_figure(
        df_counts,
        top_n,
        start_date,
        end_date,
        resample_sel,
        top_n_species,
        hourly,
        species,
        df5,
    )
    assert isinstance(fig, go.Figure)


def test_generate_multi_day_species_and_hourly_plot_should_return_figure(
    plotting_manager, mock_data_preparation_manager, sample_dataframe
):
    """Should return a plotly figure for multi-day species and hourly plots."""
    df = sample_dataframe
    resample_sel = "H"
    start_date = "2023-01-01"
    end_date = "2023-01-02"
    top_n = 3
    species = "Common Blackbird"

    # Create a MultiDayPlotConfig instance
    config = MultiDayPlotConfig(resample_sel=resample_sel, specie=species, top_n=top_n)

    # Mock the internal data preparation method that PlottingManager calls
    mock_data_preparation_manager.prepare_multi_day_plot_data.return_value = (
        pd.DataFrame(),
        pd.DataFrame({"col1": [1, 2]}, index=["SpeciesA", "Common Blackbird"]),
        pd.Series(),
        0,
    )
    mock_data_preparation_manager.get_daily_crosstab.return_value = pd.DataFrame(
        {"col1": [1, 2]}, index=["SpeciesA", "Common Blackbird"]
    )
    plotting_manager.data_preparation_manager = mock_data_preparation_manager

    fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
        df, config.resample_sel, start_date, end_date, config.top_n, config.specie
    )
    assert isinstance(fig, go.Figure)


def test_create_daily_detections_heatmap_should_return_figure(plotting_manager):
    """Should return a plotly heatmap figure for daily detections."""
    fig_x = ["2023-01-01"]
    day_hour_freq = pd.DataFrame({"08:00": [1]}, index=["2023-01-01"])
    fig_z = [[1]]
    selected_pal = "Viridis"
    sunrise_list = [0.0]
    sunrise_text_list = ["00:00 Sunrise"]
    daysback_range = ["2023-01-01"]

    fig = plotting_manager._create_daily_detections_heatmap(
        fig_x,
        day_hour_freq,
        fig_z,
        selected_pal,
        sunrise_list,
        sunrise_text_list,
        daysback_range,
    )
    assert isinstance(fig, go.Figure)


def test_update_daily_plot_layout_should_update_figure_layout(plotting_manager):
    """Should update the layout of the daily detections plot."""
    fig = go.Figure()
    saved_time_labels = ["08:00", "09:00"]
    day_hour_freq = pd.DataFrame({"08:00": [1], "09:00": [2]}, index=["2023-01-01"])

    result_fig = plotting_manager._update_daily_plot_layout(
        fig, saved_time_labels, day_hour_freq
    )
    assert isinstance(result_fig, go.Figure)
    assert "yaxis" in result_fig.layout


def test_generate_daily_detections_plot_should_return_figure(
    plotting_manager, mock_data_preparation_manager, sample_dataframe
):
    """Should return a plotly figure for daily detections plot."""
    df = sample_dataframe
    resample_sel = "15min"
    start_date = "2023-01-01"
    species = "Common Blackbird"
    num_days_to_display = 7
    selected_pal = "Viridis"

    # Mock the internal data preparation method that PlottingManager calls
    mock_data_preparation_manager.prepare_daily_plot_data.return_value = (
        pd.DataFrame(),
        [],
        [],
        [],
    )
    mock_data_preparation_manager.prepare_sunrise_sunset_data_for_plot.return_value = (
        [],
        [],
        [],
        [],
    )
    plotting_manager.data_preparation_manager = mock_data_preparation_manager

    fig = plotting_manager.generate_daily_detections_plot(
        df, resample_sel, start_date, species, num_days_to_display, selected_pal
    )
    assert isinstance(fig, go.Figure)
