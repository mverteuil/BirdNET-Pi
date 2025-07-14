import datetime
from typing import Any

import pandas as pd
from suntime import Sun

from managers.data_preparation_manager import DataPreparationManager
from managers.database_manager import DatabaseManager
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver


class ReportingManager:
    """Manages data retrieval, processing, and reporting functionalities."""

    def __init__(
        self, db_manager: DatabaseManager, file_path_resolver: FilePathResolver
    ) -> None:
        self.db_manager = db_manager
        self.file_path_resolver = file_path_resolver
        self.config = ConfigFileParser(
            self.file_path_resolver.get_birdnet_pi_config_path()
        ).load_config()
        self.data_preparation_manager = DataPreparationManager()

    def get_data(self) -> pd.DataFrame:
        """Retrieve all detection data from the database and format it into a DataFrame."""
        df = self.db_manager.get_all_detections()
        df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
        df = df.set_index("DateTime")
        return df

    def _get_weekly_stats(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        prior_start_date: datetime.date,
        prior_end_date: datetime.date,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch total detection counts and unique species counts for the current and prior weeks."""
        current_week_stats = self.db_manager.get_detection_counts_by_date_range(
            start_date, end_date
        )
        prior_week_stats = self.db_manager.get_detection_counts_by_date_range(
            prior_start_date, prior_end_date
        )
        return current_week_stats, prior_week_stats

    def _get_top_species_data(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        prior_start_date: datetime.date,
        prior_end_date: datetime.date,
    ) -> list[dict[str, Any]]:
        """Fetch the top 10 species for the current week and their counts from the prior week."""
        top_10_species_rows = self.db_manager.get_top_species_with_prior_counts(
            start_date, end_date, prior_start_date, prior_end_date
        )

        top_10_species = []
        if top_10_species_rows:
            for row in top_10_species_rows:
                current_count = row["current_count"]
                prior_count = row["prior_count"]
                percentage_diff = 0
                if prior_count > 0:
                    percentage_diff = round(
                        ((current_count - prior_count) / prior_count) * 100
                    )

                top_10_species.append(
                    {
                        "com_name": row["com_name"],
                        "count": current_count,
                        "percentage_diff": percentage_diff,
                    }
                )
        return top_10_species

    def _get_new_species_data(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[dict[str, Any]]:
        """Fetch new species detected in the current week that were not present in prior data."""
        new_species_rows = self.db_manager.get_new_species_data(start_date, end_date)
        new_species = (
            [
                {"com_name": row["com_name"], "count": row["count"]}
                for row in new_species_rows
            ]
            if new_species_rows
            else []
        )
        return new_species

    def _calculate_percentage_differences(
        self,
        total_detections_current: int,
        unique_species_current: int,
        total_detections_prior: int,
        unique_species_prior: int,
    ) -> tuple[int, int]:
        """Calculate percentage differences for total detections and unique species."""
        percentage_diff_total = 0
        if total_detections_prior > 0:
            percentage_diff_total = round(
                (
                    (total_detections_current - total_detections_prior)
                    / total_detections_prior
                )
                * 100
            )

        percentage_diff_unique_species = 0
        if unique_species_prior > 0:
            percentage_diff_unique_species = round(
                ((unique_species_current - unique_species_prior) / unique_species_prior)
                * 100
            )
        return percentage_diff_total, percentage_diff_unique_species

    def get_weekly_report_data(self) -> dict[str, Any]:
        """Retrieve and process data for the weekly report."""
        today = datetime.date.today()
        # Sunday of the week that just finished
        last_sunday = today - datetime.timedelta(days=today.weekday() + 1)
        start_date = last_sunday - datetime.timedelta(days=6)
        end_date = last_sunday

        # Calculate dates for the prior week
        prior_start_date = start_date - datetime.timedelta(days=7)
        prior_end_date = end_date - datetime.timedelta(days=7)

        current_week_stats, prior_week_stats = self._get_weekly_stats(
            start_date, end_date, prior_start_date, prior_end_date
        )

        top_10_species = self._get_top_species_data(
            start_date, end_date, prior_start_date, prior_end_date
        )

        new_species = self._get_new_species_data(start_date, end_date)

        # Extract counts
        total_detections_current = (
            current_week_stats["total_count"] if current_week_stats else 0
        )
        unique_species_current = (
            current_week_stats["unique_species"] if current_week_stats else 0
        )
        total_detections_prior = (
            prior_week_stats["total_count"] if prior_week_stats else 0
        )
        unique_species_prior = (
            prior_week_stats["unique_species"] if prior_week_stats else 0
        )

        percentage_diff_total, percentage_diff_unique_species = (
            self._calculate_percentage_differences(
                total_detections_current,
                unique_species_current,
                total_detections_prior,
                unique_species_prior,
            )
        )

        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "week_number": start_date.isocalendar()[1],
            "total_detections_current": total_detections_current,
            "unique_species_current": unique_species_current,
            "total_detections_prior": total_detections_prior,
            "unique_species_prior": unique_species_prior,
            "percentage_diff_total": percentage_diff_total,
            "percentage_diff_unique_species": percentage_diff_unique_species,
            "top_10_species": top_10_species,
            "new_species": new_species,
        }

    def get_most_recent_detections(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve the most recent detection records from the database."""
        recent_detections = self.db_manager.get_most_recent_detections(limit)
        return recent_detections

    def date_filter(
        self, df: pd.DataFrame, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Filter a DataFrame by date range."""
        filt = (df.index >= pd.Timestamp(start_date)) & (
            df.index <= pd.Timestamp(end_date + datetime.timedelta(days=1))
        )
        df = df[filt]
        return df

    def get_sunrise_sunset_data(
        self, num_days_to_display: int
    ) -> tuple[list[Any], list[Any], list[Any]]:
        """Retrieve sunrise and sunset data for a given number of days."""
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
            d = datetime.timedelta(days=num_days_to_display - past_day - 1)

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

    def get_daily_detection_data_for_plotting(
        self, df: pd.DataFrame, resample_sel: str, specie: str
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare daily detection data for plotting."""
        df4 = df["Com_Name"][df["Com_Name"] == specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [
            self.data_preparation_manager.hms_to_str(h)
            for h in day_hour_freq.columns.tolist()
        ]
        fig_dec_y = [
            self.data_preparation_manager.hms_to_dec(h)
            for h in day_hour_freq.columns.tolist()
        ]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

        return day_hour_freq, saved_time_labels, fig_dec_y, fig_x
