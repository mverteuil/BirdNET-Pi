import datetime
import io
from unittest.mock import Mock

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.models.config import BirdNETConfig
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
def plotting_manager(mock_data_preparation_manager):
    """Provide a PlottingManager instance with mocked dependencies."""
    return PlottingManager(mock_data_preparation_manager)


@pytest.fixture
def sample_dataframe():
    """Provide a sample DataFrame for testing plotting methods."""
    data = {
        "common_name": [
            "Common Blackbird",
            "Eurasian Robin",
            "Common Blackbird",
            "Eurasian Robin",
            "House Sparrow",
        ],
        "datetime": [
            datetime.datetime(2023, 1, 1, 8, 0, 0),
            datetime.datetime(2023, 1, 1, 9, 0, 0),
            datetime.datetime(2023, 1, 1, 10, 0, 0),
            datetime.datetime(2023, 1, 2, 8, 0, 0),
            datetime.datetime(2023, 1, 2, 9, 0, 0),
        ],
    }
    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    return df


def test_add_polar_trace_to_figure_should_return_figure(plotting_manager):
    """Should return a plotly figure after adding a polar trace."""
    fig = go.Figure()
    hourly_df = pd.DataFrame({"All": [1, 2, 3]}, index=pd.Index([0, 1, 2]))
    species = "Common Blackbird"
    result_fig = plotting_manager._add_polar_trace_to_figure(fig, hourly_df, species)
    assert isinstance(result_fig, go.Figure)


def test_create_multi_day_plot_figure_should_return_figure(
    plotting_manager, mock_data_preparation_manager
):
    """Should return a plotly figure for multi-day plots."""
    df_counts = 10
    top_n_count = 5
    start_date = "2023-01-01"
    end_date = "23-01-07"
    resample_selection = "D"
    top_n_species = pd.Series([5, 3], index=["SpeciesA", "SpeciesB"])
    hourly = pd.DataFrame({"All": [1, 2, 3]}, index=pd.Index([0, 1, 2]))
    species = "SpeciesA"
    df5 = pd.DataFrame(
        {
            "common_name": ["SpeciesA", "SpeciesB"],
            "datetime": [datetime.datetime(2023, 1, 1), datetime.datetime(2023, 1, 2)],
        }
    ).set_index("datetime")

    # Mock the delegated calls
    mock_data_preparation_manager.get_daily_crosstab.return_value = pd.DataFrame(
        {"col1": [1, 2]}, index=["SpeciesA", "SpeciesB"]
    )

    fig = plotting_manager._create_multi_day_plot_figure(
        df_counts,
        top_n_count,
        start_date,
        end_date,
        resample_selection,
        top_n_species,
        hourly,
        species,
        df5,
    )
    assert isinstance(fig, go.Figure)


def test_generate_multi_day_species__hourly_plot_should_return_figure(
    plotting_manager, mock_data_preparation_manager, sample_dataframe
):
    """Should return a plotly figure for multi-day species and hourly plots."""
    df = sample_dataframe
    resample_selection = "H"
    start_date = "2023-01-01"
    end_date = "2023-01-02"
    top_n_count = 3
    species = "Common Blackbird"

    # Mock the internal data preparation method that PlottingManager calls
    mock_data_preparation_manager.prepare_multi_day_plot_data.return_value = (
        pd.DataFrame(),
        pd.DataFrame(data={"col1": [1, 2]}, index=["SpeciesA", "Common Blackbird"]),
        pd.Series(),
        0,
    )
    mock_data_preparation_manager.get_daily_crosstab.return_value = pd.DataFrame(
        {"col1": [1, 2]}, index=["SpeciesA", "Common Blackbird"]
    )

    fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
        df, resample_selection, start_date, end_date, top_n_count, species
    )
    assert isinstance(fig, go.Figure)


def test_create_daily_detections_heatmap_should_return_figure(plotting_manager):
    """Should return a plotly heatmap figure for daily detections."""
    fig_x = ["2023-01-01"]
    day_hour_freq = pd.DataFrame(data={"08:00": [1]}, index=["2023-01-01"])
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
    day_hour_freq = pd.DataFrame(data={"08:00": [1], "09:00": [2]}, index=["2023-01-01"])

    result_fig = plotting_manager._update_daily_plot_layout(fig, saved_time_labels, day_hour_freq)
    assert isinstance(result_fig, go.Figure)
    assert "yaxis" in result_fig.layout


def test_generate_daily_detections_plot_should_return_figure(
    plotting_manager, mock_data_preparation_manager, sample_dataframe
):
    """Should return a plotly figure for daily detections plot."""
    df = sample_dataframe
    resample_selection = "15min"
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

    fig = plotting_manager.generate_daily_detections_plot(
        df, resample_selection, start_date, species, num_days_to_display, selected_pal
    )
    assert isinstance(fig, go.Figure)


def test_create__empty_plot(plotting_manager):
    """Should create an empty plot with a message (covers lines 28-43)."""
    message = "No data available"

    fig = plotting_manager._create_empty_plot(message)

    assert isinstance(fig, go.Figure)
    # Check the annotation was added
    assert len(fig.layout.annotations) == 1  # type: ignore[attr-defined]
    assert fig.layout.annotations[0].text == message  # type: ignore[attr-defined]
    assert fig.layout.annotations[0].x == 0.5  # type: ignore[attr-defined]
    assert fig.layout.annotations[0].y == 0.5  # type: ignore[attr-defined]
    # Check layout was updated
    assert fig.layout.xaxis.showgrid is False  # type: ignore[attr-defined]
    assert fig.layout.yaxis.showgrid is False  # type: ignore[attr-defined]
    assert fig.layout.plot_bgcolor == "white"  # type: ignore[attr-defined]


def test_generate_spectrogram(plotting_manager, mocker):
    """Should generate a spectrogram and return it as BytesIO (covers lines 47-63)."""
    # Mock librosa functions
    mock_load = mocker.patch("birdnetpi.managers.plotting_manager.librosa.load")
    mock_stft = mocker.patch("birdnetpi.managers.plotting_manager.librosa.stft")
    mock_amplitude_to_db = mocker.patch(
        "birdnetpi.managers.plotting_manager.librosa.amplitude_to_db"
    )
    mock_specshow = mocker.patch("birdnetpi.managers.plotting_manager.librosa.display.specshow")
    mock_plt = mocker.patch("birdnetpi.managers.plotting_manager.plt")

    # Setup mock returns
    mock_load.return_value = (np.array([0.1, 0.2, 0.3]), 22050)  # (audio, sample_rate)
    mock_stft.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
    mock_amplitude_to_db.return_value = np.array([[0.5, 0.6], [0.7, 0.8]])

    # Mock the figure and axes
    mock_fig = Mock()
    mock_ax = Mock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    # Call the method
    audio_path = "/path/to/audio.wav"
    result = plotting_manager.generate_spectrogram(audio_path)

    # Verify the function calls
    mock_load.assert_called_once_with(audio_path)
    mock_stft.assert_called_once()
    mock_amplitude_to_db.assert_called_once()
    mock_specshow.assert_called_once()
    mock_ax.set.assert_called_once_with(title="Spectrogram")
    mock_fig.tight_layout.assert_called_once()
    mock_plt.savefig.assert_called_once()
    mock_plt.close.assert_called_once_with(mock_fig)

    # Verify result is a BytesIO
    assert isinstance(result, io.BytesIO)


def test_generate_multi_day_plot___empty_dataframe(plotting_manager, mocker):
    """Should return empty plot when dataframe is empty (covers line 181)."""
    # Create empty DataFrame
    empty_df = pd.DataFrame()

    # Mock the _create_empty_plot method to verify it's called
    mock_create_empty = mocker.patch.object(plotting_manager, "_create_empty_plot")
    mock_create_empty.return_value = go.Figure()

    # Call the method with empty DataFrame
    result = plotting_manager.generate_multi_day_species_and_hourly_plot(
        empty_df, "H", "2023-01-01", "2023-01-02", 3, "Common Blackbird"
    )

    # Verify _create_empty_plot was called with correct message
    mock_create_empty.assert_called_once_with("No data available for multi-day plot")
    assert isinstance(result, go.Figure)


def test_generate_daily_detections_plot___empty_dataframe(plotting_manager, mocker):
    """Should return empty plot when dataframe is empty (covers line 264)."""
    # Create empty DataFrame
    empty_df = pd.DataFrame()

    # Mock the _create_empty_plot method to verify it's called
    mock_create_empty = mocker.patch.object(plotting_manager, "_create_empty_plot")
    mock_create_empty.return_value = go.Figure()

    # Call the method with empty DataFrame
    result = plotting_manager.generate_daily_detections_plot(
        empty_df, "15min", "2023-01-01", "Common Blackbird", 7, "Viridis"
    )

    # Verify _create_empty_plot was called with correct message
    mock_create_empty.assert_called_once_with("No data available for daily plot")
    assert isinstance(result, go.Figure)
