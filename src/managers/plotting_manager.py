import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from suntime import Sun

from managers.database_manager import DatabaseManager
from utils.file_path_resolver import FilePathResolver


class PlottingManager:
    def __init__(
        self, db_manager: DatabaseManager, file_path_resolver: FilePathResolver
    ):
        self.db_manager = db_manager
        self.file_path_resolver = file_path_resolver

    @staticmethod
    def hms_to_dec(t):
        """Converts a datetime.time object to its decimal hour representation."""
        h = t.hour
        m = t.minute / 60
        s = t.second / 3600
        result = h + m + s
        return result

    @staticmethod
    def hms_to_str(t):
        """Converts a datetime.time object to a formatted string (HH:MM)."""
        h = t.hour
        m = t.minute
        return "%02d:%02d" % (h, m)

    def get_species_counts(self, df: pd.DataFrame) -> pd.Series:
        """Calculates the counts of each common name in the DataFrame."""
        return df["Com_Name"].value_counts()

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generates a crosstabulation of common names by hour."""
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generates a crosstabulation of common names by date."""
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

    def _add_polar_trace_to_figure(self, fig, hourly, specie):
        # Placeholder for the actual implementation of _add_polar_trace_to_figure
        # This method was not present in the original ReportingManager, but is called by _create_multi_day_plot_figure
        return fig

    def _create_multi_day_plot_figure(
        self,
        df_counts: int,
        top_N: int,
        start_date: str,
        end_date: str,
        resample_sel: str,
        top_N_species: pd.Series,
        hourly: pd.DataFrame,
        specie: str,
        df5: pd.DataFrame,
    ) -> go.Figure:
        """Creates a Plotly figure for multi-day species and hourly plots."""
        fig = make_subplots(
            rows=3,
            cols=2,
            specs=[
                [{"type": "xy", "rowspan": 3}, {"type": "polar", "rowspan": 2}],
                [{"rowspan": 1}, {"rowspan": 1}],
                [None, {"type": "xy", "rowspan": 1}],
            ],
            subplot_titles=(
                "<b>Top "
                + str(top_N)
                + " Species in Date Range "
                + str(start_date)
                + " to "
                + str(end_date)
                + "<br>for "
                + str(resample_sel)
                + " sampling interval."
                + "</b>",
                "Total Detect:" + str("{:,}".format(df_counts)),
            ),
        )
        fig.layout.annotations[1].update(x=0.7, y=0.25, font_size=15)

        fig.add_trace(
            go.Bar(
                y=top_N_species.index,
                x=top_N_species,
                orientation="h",
                marker_color="seagreen",
            ),
            row=1,
            col=1,
        )

        fig.update_layout(
            margin=dict(l=0, r=0, t=50, b=0),
            yaxis={"categoryorder": "total ascending"},
        )

        fig = self._add_polar_trace_to_figure(fig, hourly, specie)

        daily = self.get_daily_crosstab(df5)
        fig.add_trace(
            go.Bar(
                x=daily.columns[:-1],
                y=daily.loc[specie][:-1],
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
        top_N: int,
        specie: str,
    ) -> go.Figure:
        """Generates a multi-day species and hourly plot."""
        df5, hourly, top_N_species, df_counts = self._prepare_multi_day_plot_data(
            df, resample_sel, specie, top_N
        )

        fig = self._create_multi_day_plot_figure(
            df_counts,
            top_N,
            start_date,
            end_date,
            resample_sel,
            top_N_species,
            hourly,
            specie,
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
        """Creates a Plotly heatmap figure for daily detections."""
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

    def _update_daily_plot_layout(self, fig, saved_time_labels, day_hour_freq):
        """Updates the layout of the daily detections plot, specifically the y-axis ticks."""
        number_of_y_ticks = 12
        y_downscale_factor = int(len(saved_time_labels) / number_of_y_ticks)
        fig.update_layout(
            yaxis=dict(
                tickmode="array",
                tickvals=day_hour_freq.columns[::y_downscale_factor],
                ticktext=saved_time_labels[::y_downscale_factor],
                nticks=6,
            )
        )
        return fig

    def generate_daily_detections_plot(
        self,
        df: pd.DataFrame,
        resample_sel: str,
        start_date: str,
        specie: str,
        num_days_to_display: int,
        selected_pal: str,
    ) -> go.Figure:
        """Generates a daily detections plot."""
        day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
            self._prepare_daily_plot_data(df, resample_sel, specie)
        )

        day_hour_freq.columns = fig_dec_y
        fig_z = day_hour_freq.values.transpose()

        sunrise_week_list, sunrise_list, sunrise_text_list, daysback_range = (
            self._prepare_sunrise_sunset_data_for_plot(num_days_to_display, fig_x)
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
