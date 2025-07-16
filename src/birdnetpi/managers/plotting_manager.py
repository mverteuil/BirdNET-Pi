import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.models.multi_day_plot_config import MultiDayPlotConfig


class PlottingManager:
    """Manages the creation and manipulation of various plots and visualizations."""

    def __init__(self) -> None:
        self.data_preparation_manager = DataPreparationManager()

    def _add_polar_trace_to_figure(
        self, fig: go.Figure, hourly: pd.DataFrame, species: str
    ) -> go.Figure:
        """Add a polar trace to the given Plotly figure."""
        # Placeholder for the actual implementation of _add_polar_trace_to_figure
        # This method was not present in the original ReportingManager, but is called by _create_multi_day_plot_figure
        return fig

    def _create_multi_day_plot_figure(
        self,
        df_counts: int,
        top_n: int,
        start_date: str,
        end_date: str,
        resample_sel: str,
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
                f"<b>Top {top_n} Species in Date Range {start_date} to "
                f"{end_date}<br>for {resample_sel} sampling interval.</b>",
                f"Total Detect:{df_counts:,}",
            ),
        )
        fig.layout.annotations[1].update(x=0.7, y=0.25, font_size=15)

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

        # Assuming get_daily_crosstab is now in ReportingManager and passed as part of df5 or similar
        # For now, keeping it as a method that takes df5
        daily_crosstab = self.data_preparation_manager.get_daily_crosstab(
            df5
        )  # This method should be moved to ReportingManager

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
        resample_sel: str,
        start_date: str,
        end_date: str,
        top_n: int,
        species: str,
    ) -> go.Figure:
        """Generate a multi-day species and hourly plot."""
        config = MultiDayPlotConfig(
            resample_sel=resample_sel, specie=species, top_n=top_n
        )
        df5, hourly, top_n_species, df_counts = (
            self.data_preparation_manager.prepare_multi_day_plot_data(df, config)
        )

        fig = self._create_multi_day_plot_figure(
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
        resample_sel: str,
        start_date: str,
        species: str,
        num_days_to_display: int,
        selected_pal: str,
    ) -> go.Figure:
        """Generate a daily detections plot."""
        day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
            self.data_preparation_manager.prepare_daily_plot_data(
                df, resample_sel, species
            )
        )

        day_hour_freq.columns = fig_dec_y
        fig_z = day_hour_freq.values.transpose()

        sunrise_week_list, sunrise_list, sunrise_text_list, daysback_range = (
            self.data_preparation_manager.prepare_sunrise_sunset_data_for_plot(
                num_days_to_display, fig_x
            )
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
