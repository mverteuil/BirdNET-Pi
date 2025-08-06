import datetime
from typing import cast

import pandas as pd

from birdnetpi.models.config import BirdNETConfig, DailyPlotConfig, MultiDayPlotConfig
from birdnetpi.services.location_service import LocationService


class DataPreparationManager:
    """Manages data preparation and manipulation for reporting and plotting."""

    def __init__(
        self,
        config: BirdNETConfig,
        location_service: LocationService,
    ) -> None:
        self.config = config
        self.location_service = location_service

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
        return df["common_name_ioc"].value_counts()

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by hour."""
        datetime_index = cast(pd.DatetimeIndex, df.index)
        return pd.crosstab(df["common_name_ioc"], datetime_index.hour.values, dropna=True, margins=True)  # type: ignore[attr-defined]

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by date."""
        datetime_index = cast(pd.DatetimeIndex, df.index)
        return pd.crosstab(df["common_name_ioc"], datetime_index.date, dropna=True, margins=True)  # type: ignore[attr-defined]

    def time_resample(self, df: pd.DataFrame, resample_time: str) -> pd.DataFrame:
        """Resample the DataFrame based on the given time interval."""
        if resample_time == "Raw":
            df_resample = df[["common_name_ioc"]]
        else:
            series_result = (
                df.resample(resample_time.lower())["common_name_ioc"].aggregate("unique").explode()
            )
            df_resample = series_result.to_frame()
        return cast(pd.DataFrame, df_resample)

    def prepare_multi_day_plot_data(
        self, df: pd.DataFrame, config: MultiDayPlotConfig
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, int]:
        """Prepare data for the multi-day species and hourly plot."""
        df5 = self.time_resample(df, config.resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_n_species = self.get_species_counts(df5)[: config.top_n]

        counts_series = hourly[hourly.index == config.species]["All"]
        counts_series_cast = cast(pd.Series, counts_series)
        df_counts = int(counts_series_cast.iloc[0]) if len(counts_series_cast) > 0 else 0
        return df5, hourly, cast(pd.Series, top_n_species), df_counts

    def prepare_daily_plot_data(
        self, df: pd.DataFrame, config: DailyPlotConfig
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare data for the daily detections plot."""
        # Filter the DataFrame first, then get the series and resample
        # Ensure we're working with proper pandas objects by accessing the series directly
        species_mask = df["common_name_ioc"] == config.species
        species_series = df.loc[species_mask, "common_name_ioc"]
        df4 = cast(pd.Series, species_series.resample("15min").count())
        datetime_index = cast(pd.DatetimeIndex, df4.index)
        df4.index = [datetime_index.date, datetime_index.time]  # type: ignore[attr-defined]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = []
        for d in day_hour_freq.index.tolist():
            if hasattr(d, "strftime"):
                fig_x.append(d.strftime("%d-%m-%Y"))  # type: ignore[attr-defined]
            else:
                fig_x.append(str(d))

        # Ensure we return consistent types
        return cast(pd.DataFrame, day_hour_freq), saved_time_labels, fig_dec_y, fig_x

    def prepare_sunrise_sunset_data_for_plot(
        self, num_days_to_display: int
    ) -> tuple[list, list, list, list]:
        """Prepare sunrise and sunset data for plotting."""
        (sunrise_times_dec, sunset_times_dec, dates_str, sunrise_text, sunset_text) = (
            self.get_sunrise_sunset_data(num_days_to_display)
        )

        # Prepare data for plotting
        # The x-axis for both sunrise and sunset will be the dates_str, but we need to repeat them
        # to create a continuous line for each (sunrise and sunset).
        # The y-axis will be the decimal hour representation of sunrise/sunset times.
        # The text labels will be used for hover information on the plot.

        # Combine sunrise and sunset data for plotting
        plot_x = dates_str + dates_str
        plot_y = sunrise_times_dec + sunset_times_dec
        plot_text = sunrise_text + sunset_text

        # Create a list of colors for the plot, e.g., 'orange' for sunrise and 'purple' for sunset
        plot_colors = ["orange"] * len(sunrise_times_dec) + ["purple"] * len(sunset_times_dec)

        return plot_x, plot_y, plot_text, plot_colors

    def get_sunrise_sunset_data(
        self, num_days_to_display: int
    ) -> tuple[list, list, list, list, list]:
        """Retrieve sunrise and sunset data for a given number of days."""
        sunrise_times_dec = []
        sunset_times_dec = []
        dates_str = []
        sunrise_text = []
        sunset_text = []

        for past_day in range(num_days_to_display):
            current_date = datetime.date.today() - datetime.timedelta(days=past_day)
            sunrise_time, sunset_time = self.location_service.get_sunrise_sunset_times(current_date)

            sunrise_times_dec.append(self.hms_to_dec(sunrise_time.time()))
            sunset_times_dec.append(self.hms_to_dec(sunset_time.time()))
            dates_str.append(current_date.strftime("%Y-%m-%d"))
            sunrise_text.append(f"{self.hms_to_str(sunrise_time.time())} Sunrise")
            sunset_text.append(f"{self.hms_to_str(sunset_time.time())} Sunset")

        return sunrise_times_dec, sunset_times_dec, dates_str, sunrise_text, sunset_text
