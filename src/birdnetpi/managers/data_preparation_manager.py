import datetime

import pandas as pd

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.daily_plot_config import DailyPlotConfig
from birdnetpi.models.multi_day_plot_config import MultiDayPlotConfig
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
        return df["com_name"].value_counts()

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by hour."""
        return pd.crosstab(df["com_name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by date."""
        return pd.crosstab(df["com_name"], df.index.date, dropna=True, margins=True)

    def time_resample(self, df: pd.DataFrame, resample_time: str) -> pd.DataFrame:
        """Resample the DataFrame based on the given time interval."""
        if resample_time == "Raw":
            df_resample = df[["com_name"]]
        else:
            df_resample = (
                df.resample(resample_time.lower())["com_name"]
                .aggregate("unique")
                .explode()
                .to_frame()
            )
        return df_resample

    def prepare_multi_day_plot_data(
        self, df: pd.DataFrame, config: MultiDayPlotConfig
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, int]:
        """Prepare data for the multi-day species and hourly plot."""
        df5 = self.time_resample(df, config.resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_n_species = self.get_species_counts(df5)[: config.top_n]

        df_counts = int(hourly[hourly.index == config.specie]["All"].iloc[0])
        return df5, hourly, top_n_species, df_counts

    def prepare_daily_plot_data(
        self, df: pd.DataFrame, config: DailyPlotConfig
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare data for the daily detections plot."""
        df4 = df["com_name"][df["com_name"] == config.specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

        return day_hour_freq, saved_time_labels, fig_dec_y, fig_x

    def prepare_sunrise_sunset_data_for_plot(
        self, num_days_to_display: int, fig_x: list[str]
    ) -> tuple[list, list, list, list]:
        """Prepare sunrise and sunset data for plotting."""
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
        sunrise_list = []
        sunset_list = []
        sunrise_week_list = []
        sunset_week_list = []
        sunrise_text_list = []
        sunset_text_list = []

        for past_day in range(num_days_to_display):
            current_date = datetime.now().date() - datetime.timedelta(days=past_day)
            sunrise_time, sunset_time = self.location_service.get_sunrise_sunset_times(
                current_date
            )

            sunrise_list.append(self.hms_to_dec(sunrise_time.time()))
            sunset_list.append(self.hms_to_dec(sunset_time.time()))
            sunrise_text_list.append(f"{self.hms_to_str(sunrise_time.time())} Sunrise")
            sunset_text_list.append(f"{self.hms_to_str(sunset_time.time())} Sunset")
            sunrise_week_list.append(past_day)
            sunset_week_list.append(past_day)

        sunrise_week_list.append(None)
        sunrise_list.append(None)
        sunrise_text_list.append(None)
        sunrise_list.extend(sunset_list)
        sunrise_week_list.extend(sunset_week_list)
        sunrise_text_list.extend(sunset_text_list)

        return sunrise_week_list, sunrise_list, sunrise_text_list
