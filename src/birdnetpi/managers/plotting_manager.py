import io

import matplotlib

# Ensure matplotlib uses non-GUI backend BEFORE any other matplotlib imports
matplotlib.use("Agg")

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from birdnetpi.managers.data_preparation_manager import DataPreparationManager


class PlottingManager:
    """Manages the creation and manipulation of various plots and visualizations."""

    def __init__(self, data_preparation_manager: DataPreparationManager) -> None:
        self.data_preparation_manager = data_preparation_manager

    def _create_empty_plot(self, message: str) -> go.Figure:
        """Create an empty plot with a message when no data is available."""
        fig = go.Figure()
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text=message,
            showarrow=False,
            font={"size": 16},
            xref="paper",
            yref="paper",
        )
        fig.update_layout(
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            plot_bgcolor="white",
        )
        return fig

    def generate_spectrogram(self, audio_path: str) -> io.BytesIO:
        """Generate a spectrogram for a given audio file and return it as a BytesIO buffer."""
        y, sr = librosa.load(audio_path)

        # Compute spectrogram
        d = librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max)

        # Create plot
        fig, ax = plt.subplots(figsize=(10, 5))
        librosa.display.specshow(d, sr=sr, x_axis="time", y_axis="log", ax=ax)
        ax.set(title="Spectrogram")
        fig.tight_layout()

        # Save plot to a bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)  # Close the figure to free memory
        buf.seek(0)
        return buf

    def _add_polar_trace_to_figure(
        self, fig: go.Figure, hourly: pd.DataFrame, species: str
    ) -> go.Figure:
        """Add a polar trace to the given Plotly figure."""
        # Check if the species exists in the hourly data
        if species in hourly.index:
            r_values = hourly.loc[species][:-1]  # Exclude 'All' column
            theta_values = hourly.columns[:-1]  # Exclude 'All' column

            # Convert theta_values (hours) to degrees for polar plot (0-24h to 0-360 degrees)
            theta_degrees = [
                h * 15 for h in theta_values
            ]  # 24 hours * 15 degrees/hour = 360 degrees

            fig.add_trace(
                go.Scatterpolar(
                    r=r_values,
                    theta=theta_degrees,
                    mode="lines",
                    name=species,
                    thetaunit="degrees",
                    line_color="darkgreen",
                    fill="toself",
                    fillcolor="rgba(0,100,0,0.2)",
                ),
                row=1,
                col=2,
            )

            fig.update_layout(
                polar={
                    "radialaxis_visible": True,
                    "angularaxis": {
                        "tickmode": "array",
                        "tickvals": [0, 90, 180, 270],
                        "ticktext": ["0h", "6h", "12h", "18h"],
                        "direction": "clockwise",
                        "rotation": 90,
                    },
                }
            )
        return fig

    def _create_multi_day_plot_figure(
        self,
        df_counts: int,
        top_n_count: int,
        start_date: str,
        end_date: str,
        resample_selection: str,
        top_n_species: pd.Series,
        hourly: pd.DataFrame,
        species: str,
        df5: pd.DataFrame,
    ) -> go.Figure:
        """Create a Plotly figure for multi-day species and hourly plots."""
        fig = make_subplots(
            rows=3,
            cols=2,
            specs=[
                [{"type": "xy", "rowspan": 3}, {"type": "polar", "rowspan": 2}],
                [{"rowspan": 1}, {"rowspan": 1}],
                [None, {"type": "xy", "rowspan": 1}],
            ],
            subplot_titles=(
                f"<b>Top {top_n_count} Species in Date Range {start_date} to "
                f"{end_date}<br>for {resample_selection} sampling interval.</b>",
                f"Total Detect:{df_counts:,}",
            ),
        )
        fig.layout.annotations[1].update(x=0.7, y=0.25, font_size=15)  # type: ignore[index]

        fig.add_trace(
            go.Bar(
                y=top_n_species.index,
                x=top_n_species,
                orientation="h",
                marker_color="seagreen",
            ),
            row=1,
            col=1,
        )

        fig.update_layout(
            margin={"l": 0, "r": 0, "t": 50, "b": 0},
            yaxis={"categoryorder": "total ascending"},
        )

        fig = self._add_polar_trace_to_figure(fig, hourly, species)

        # get_daily_crosstab is in DataPreparationManager and takes df5 as input
        daily_crosstab = self.data_preparation_manager.get_daily_crosstab(df5)

        fig.add_trace(
            go.Bar(
                x=daily_crosstab.columns[:-1],
                y=daily_crosstab.loc[species][:-1],
                marker_color="seagreen",
            ),
            row=3,
            col=2,
        )
        return fig

    def generate_multi_day_species_and_hourly_plot(
        self,
        df: pd.DataFrame,
        resample_selection: str,
        start_date: str,
        end_date: str,
        top_n_count: int,
        species: str,
    ) -> go.Figure:
        """Generate a multi-day species and hourly plot."""
        # Handle empty DataFrame case or DataFrame with no actual data
        if df.empty or len(df) == 0:
            return self._create_empty_plot("No data available for multi-day plot")

        df5, hourly, top_n_species, df_counts = (
            self.data_preparation_manager.prepare_multi_day_plot_data(
                df, resample_selection, species, top_n_count
            )
        )

        fig = self._create_multi_day_plot_figure(
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
        return fig

    def _create_daily_detections_heatmap(
        self,
        fig_x: list,
        day_hour_freq: pd.DataFrame,
        fig_z: np.ndarray,
        selected_pal: str,
        sunrise_list: list,
        sunrise_text_list: list,
        daysback_range: list,
    ) -> go.Figure:
        """Create a Plotly heatmap figure for daily detections."""
        heatmap = go.Heatmap(
            x=fig_x,
            y=day_hour_freq.columns,
            z=fig_z,
            showscale=False,
            texttemplate="%{text}",
            autocolorscale=False,
            colorscale=selected_pal,
        )

        sunrise_sunset = go.Scatter(
            x=daysback_range,
            y=sunrise_list,
            mode="lines",
            hoverinfo="text",
            text=sunrise_text_list,
            line_color="orange",
            line_width=1,
            name=" ",
        )

        fig = go.Figure(data=[heatmap, sunrise_sunset])
        return fig

    def _update_daily_plot_layout(
        self, fig: go.Figure, saved_time_labels: list, day_hour_freq: pd.DataFrame
    ) -> go.Figure:
        """Update the layout of the daily detections plot, specifically the y-axis ticks."""
        number_of_y_ticks = 12
        y_downscale_factor = max(1, int(len(saved_time_labels) / number_of_y_ticks))
        fig.update_layout(
            yaxis={
                "tickmode": "array",
                "tickvals": day_hour_freq.columns[::y_downscale_factor],
                "ticktext": saved_time_labels[::y_downscale_factor],
                "nticks": 6,
            }
        )
        return fig

    def generate_daily_detections_plot(
        self,
        df: pd.DataFrame,
        resample_selection: str,
        start_date: str,
        species: str,
        num_days_to_display: int,
        selected_pal: str,
    ) -> go.Figure:
        """Generate a daily detections plot."""
        # Handle empty DataFrame case or DataFrame with no actual data
        if df.empty or len(df) == 0:
            return self._create_empty_plot("No data available for daily plot")

        day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
            self.data_preparation_manager.prepare_daily_plot_data(df, resample_selection, species)
        )

        day_hour_freq.columns = fig_dec_y
        fig_z = day_hour_freq.values.transpose()

        sunrise_week_list, sunrise_list, sunrise_text_list, daysback_range = (
            self.data_preparation_manager.prepare_sunrise_sunset_data_for_plot(num_days_to_display)
        )

        fig = self._create_daily_detections_heatmap(
            fig_x,
            day_hour_freq,
            fig_z,
            selected_pal,
            sunrise_list,
            sunrise_text_list,
            daysback_range,
        )

        fig = self._update_daily_plot_layout(fig, saved_time_labels, day_hour_freq)
        return fig
