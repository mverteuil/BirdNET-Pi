import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class PlottingManager:
    """Manages the creation and manipulation of various plots and visualizations."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def hms_to_dec(time_obj: datetime.time) -> float:
        """Convert a datetime.time object to its decimal hour representation."""
        hour = time_obj.hour
        minute = time_obj.minute / 60
        second = time_obj.second / 3600
        result = hour + minute + second
        return result

    @staticmethod
    def hms_to_str(time_obj: datetime.time) -> str:
        """Convert a datetime.time object to a formatted string (HH:MM)."""
        hour = time_obj.hour
        minute = time_obj.minute
        return f"{hour:02d}:{minute:02d}"

    def get_species_counts(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the counts of each common name in the DataFrame."""
        return df["Com_Name"].value_counts()

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by hour."""
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by date."""
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

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
        daily_crosstab = self.get_daily_crosstab(
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
        # _prepare_multi_day_plot_data should be in ReportingManager and its output passed here
        # For now, keeping it as a method that takes df, resample_sel, species, top_n
        df5, hourly, top_n_species, df_counts = self._prepare_multi_day_plot_data(
            df, resample_sel, species, top_n
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
        y_downscale_factor = int(len(saved_time_labels) / number_of_y_ticks)
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
            self._prepare_daily_plot_data(df, resample_sel, species)
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

    # These methods are for data preparation and should be moved to ReportingManager
    def _prepare_multi_day_plot_data(
        self, df: pd.DataFrame, resample_sel: str, specie: str, top_n: int
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, int]:
        """Prepare data for the multi-day species and hourly plot."""
        df5 = self.time_resample(df, resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_n_species = self.get_species_counts(df5)[:top_n]

        df_counts = int(hourly[hourly.index == specie]["All"].iloc[0])
        return df5, hourly, top_n_species, df_counts

    def time_resample(self, df: pd.DataFrame, resample_time: str) -> pd.DataFrame:
        """Resamples the DataFrame based on the given time interval."""
        if resample_time == "Raw":
            df_resample = df["Com_Name"]
        else:
            df_resample = (
                df.resample(resample_time)["Com_Name"].aggregate("unique").explode()
            )
        return df_resample

    def _prepare_sunrise_sunset_data_for_plot(
        self, num_days_to_display: int, fig_x: list[str]
    ) -> tuple[list, list, list, list]:
        """Prepare sunrise and sunset data for plotting."""
        # This method relies on get_sunrise_sunset_data which should be in ReportingManager
        # For now, keeping it here as a placeholder
        sunrise_week_list, sunrise_list, sunrise_text_list = (
            self.get_sunrise_sunset_data(num_days_to_display)
        )
        daysback_range = fig_x
        daysback_range.append(None)
        daysback_range.extend(daysback_range)
        daysback_range = daysback_range[:-1]
        return sunrise_week_list, sunrise_list, sunrise_text_list, daysback_range

    def get_sunrise_sunset_data(
        self, num_days_to_display: int
    ) -> tuple[list, list, list]:
        """Retrieve sunrise and sunset data for a given number of days."""
        # This method relies on self.config which PlottingManager should not have
        # For now, keeping it here as a placeholder

        # sun = Sun(latitude, longitude) # Sun import removed from PlottingManager

        sunrise_list = []
        sunset_list = []
        sunrise_week_list = []
        sunset_week_list = []
        sunrise_text_list = []
        sunset_text_list = []

        for past_day in range(num_days_to_display):

            # sun_rise = sun.get_local_sunrise_time(current_date) # Sun import removed
            # sun_dusk = sun.get_local_sunset_time(current_date) # Sun import removed

            sun_rise_time = 0.0  # Placeholder
            sun_dusk_time = 0.0  # Placeholder

            temp_time = "00:00 Sunrise"  # Placeholder
            sunrise_text_list.append(temp_time)
            temp_time = "00:00 Sunset"  # Placeholder
            sunset_text_list.append(temp_time)
            sunrise_list.append(sun_rise_time)
            sunset_list.append(sun_dusk_time)
            sunrise_week_list.append(past_day)
            sunset_week_list.append(past_day)

        sunrise_week_list.append(None)
        sunrise_list.append(None)
        sunrise_text_list.append(None)
        sunrise_list.extend(sunset_list)
        sunrise_week_list.extend(sunset_week_list)
        sunrise_text_list.extend(sunset_text_list)

        return sunrise_week_list, sunrise_list, sunrise_text_list

    def _prepare_daily_plot_data(
        self, df: pd.DataFrame, resample_sel: str, specie: str
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare data for the daily detections plot."""
        df4 = df["Com_Name"][df["Com_Name"] == specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

        return day_hour_freq, saved_time_labels, fig_dec_y, fig_x
