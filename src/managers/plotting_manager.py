import datetime
from datetime import timedelta

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
        """Converts a datetime.time object to its decimal hour representation.

        Args:
            t (datetime.time): The time object.

        Returns:
            float: The time in decimal hours.
        """
        h = t.hour
        m = t.minute / 60
        s = t.second / 3600
        result = h + m + s
        return result

    @staticmethod
    def hms_to_str(t):
        """Converts a datetime.time object to a formatted string (HH:MM).

        Args:
            t (datetime.time): The time object.

        Returns:
            str: The formatted time string.
        """
        h = t.hour
        m = t.minute
        return "%02d:%02d" % (h, m)

    def get_species_counts(self, df: pd.DataFrame) -> pd.Series:
        """Calculates the counts of each common name in the DataFrame.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.

        Returns:
            pd.Series: A Series containing the counts of each common name.
        """
        return df["Com_Name"].value_counts()

    def _prepare_multi_day_plot_data(
        self, df: pd.DataFrame, resample_sel: str, specie: str, top_N: int
    ):
        """Prepares data for the multi-day species and hourly plot.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.
            resample_sel (str): Resampling interval (e.g., "15min").
            specie (str): The species to focus on for hourly data.
            top_N (int): The number of top species to retrieve.

        Returns:
            tuple: A tuple containing:
                - df5 (pd.DataFrame): Resampled DataFrame.
                - hourly (pd.DataFrame): Hourly crosstab data.
                - top_N_species (pd.Series): Top N species counts.
                - df_counts (int): Total detections for the specified species.
        """
        df5 = self.time_resample(df, resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_N_species = self.get_species_counts(df5)[:top_N]

        df_counts = int(hourly[hourly.index == specie]["All"].iloc[0])
        return df5, hourly, top_N_species, df_counts

    def generate_multi_day_species_and_hourly_plot(
        self,
        df: pd.DataFrame,
        resample_sel: str,
        start_date: str,
        end_date: str,
        top_N: int,
        specie: str,
    ) -> go.Figure:
        """Generates a multi-day species and hourly plot.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.
            resample_sel (str): Resampling interval (e.g., "15min").
            start_date (str): Start date of the data range.
            end_date (str): End date of the data range.
            top_N (int): The number of top species to retrieve.
            specie (str): The species to focus on for hourly data.

        Returns:
            go.Figure: A Plotly Figure object.
        """
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

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generates a crosstabulation of common names by hour.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.

        Returns:
            pd.DataFrame: A crosstabulation DataFrame.
        """
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generates a crosstabulation of common names by date.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.

        Returns:
            pd.DataFrame: A crosstabulation DataFrame.
        """
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

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
        """Creates a Plotly figure for multi-day species and hourly plots.

        Args:
            df_counts (int): Total detections for the specified species.
            top_N (int): The number of top species to retrieve.
            start_date (str): Start date of the data range.
            end_date (str): End date of the data range.
            resample_sel (str): Resampling interval.
            top_N_species (pd.Series): Top N species counts.
            hourly (pd.DataFrame): Hourly crosstab data.
            specie (str): The species to focus on for hourly data.
            df5 (pd.DataFrame): Resampled DataFrame.

        Returns:
            go.Figure: A Plotly Figure object containing the bar and polar traces.
        """
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

    def _prepare_daily_plot_data(
        self, df: pd.DataFrame, resample_sel: str, specie: str
    ):
        """Prepares data for the daily detections plot.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.
            resample_sel (str): Resampling interval (e.g., "15min").
            specie (str): The species to focus on for daily data.

        Returns:
            tuple: A tuple containing:
                - day_hour_freq (pd.DataFrame): Daily frequency data.
                - saved_time_labels (list): Formatted time labels.
                - fig_dec_y (list): Decimal representation of time for plotting.
                - fig_x (list): Formatted dates for plotting.
        """
        df4 = df["Com_Name"][df["Com_Name"] == specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

        return day_hour_freq, saved_time_labels, fig_dec_y, fig_x

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
        """Creates a Plotly heatmap figure for daily detections.

        Args:
            fig_x (list): Formatted dates for plotting.
            day_hour_freq (pd.DataFrame): Daily frequency data.
            fig_z (np.ndarray): Transposed 2D array of detection counts.
            selected_pal (str): Color palette for the heatmap.
            sunrise_list (list): List of sunrise times for plotting.
            sunrise_text_list (list): List of sunrise text labels for plotting.
            daysback_range (list): Range of days for plotting.

        Returns:
            go.Figure: A Plotly Figure object containing the heatmap and sunrise/sunset traces.
        """
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

    def date_filter(
        self, df: pd.DataFrame, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Filters a DataFrame by date range.

        Args:
            df (pd.DataFrame): The input DataFrame.
            start_date (str): The start date for filtering.
            end_date (str): The end date for filtering.

        Returns:
            pd.DataFrame: The filtered DataFrame.
        """
        filt = (df.index >= pd.Timestamp(start_date)) & (
            df.index <= pd.Timestamp(end_date + timedelta(days=1))
        )
        df = df[filt]
        return df

    def time_resample(self, df: pd.DataFrame, resample_time: str) -> pd.DataFrame:
        """Resamples the DataFrame based on the given time interval.

        Args:
            df (pd.DataFrame): The input DataFrame.
            resample_time (str): The resampling interval (e.g., "15min", "Raw").

        Returns:
            pd.DataFrame: The resampled DataFrame.
        """
        if resample_time == "Raw":
            df_resample = df["Com_Name"]
        else:
            df_resample = (
                df.resample(resample_time)["Com_Name"].aggregate("unique").explode()
            )
        return df_resample

    def get_sunrise_sunset_data(self, num_days_to_display: int):
        """Retrieves sunrise and sunset data for a given number of days.

        Args:
            num_days_to_display (int): The number of days to retrieve data for.

        Returns:
            tuple: A tuple containing lists of sunrise week, sunrise times, and sunrise text.
        """
        latitude = self.config.latitude
        longitude = self.config.longitude

        sun = Sun(latitude, longitude)

        sunrise_list = []
        sunset_list = []
        sunrise_week_list = []
        sunset_week_list = []
        sunrise_text_list = []
        sunset_text_list = []

        now = datetime.datetime.now()

        for past_day in range(num_days_to_display):
            d = timedelta(days=num_days_to_display - past_day - 1)

            current_date = now - d
            sun_rise = sun.get_local_sunrise_time(current_date)
            sun_dusk = sun.get_local_sunset_time(current_date)

            sun_rise_time = float(sun_rise.hour) + float(sun_rise.minute) / 60.0
            sun_dusk_time = float(sun_dusk.hour) + float(sun_dusk.minute) / 60.0

            temp_time = str(sun_rise)[-14:-9] + " Sunrise"
            sunrise_text_list.append(temp_time)
            temp_time = str(sun_dusk)[-14:-9] + " Sunset"
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

    def generate_daily_detections_plot(
        self,
        df: pd.DataFrame,
        resample_sel: str,
        start_date: str,
        specie: str,
        num_days_to_display: int,
        selected_pal: str,
    ) -> go.Figure:
        """Generates a daily detections plot.

        Args:
            df (pd.DataFrame): The input DataFrame containing detection data.
            resample_sel (str): Resampling interval (e.g., "15min").
            start_date (str): Start date of the data range.
            specie (str): The species to focus on for daily data.
            num_days_to_display (int): Number of days to display data for.
            selected_pal (str): Color palette for the heatmap.

        Returns:
            go.Figure: A Plotly Figure object.
        """
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
