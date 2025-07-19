import datetime
from typing import Any

import pandas as pd

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


class ReportingManager:
    """Manages data retrieval, processing, and reporting functionalities."""

    def __init__(
        self,
        db_manager: DetectionManager,
        file_path_resolver: FilePathResolver,
        config_parser: ConfigFileParser,
    ) -> None:
        self.detection_manager = db_manager
        self.file_path_resolver = file_path_resolver
        self.config = config_parser.load_config()
        self.data_preparation_manager = DataPreparationManager()

    def get_data(self) -> pd.DataFrame:
        """Retrieve all detection data from the database and format it into a DataFrame."""
        detections = self.detection_manager.get_all_detections()
        data = [
            {
                "Com_Name": d.species,
                "DateTime": d.timestamp,
                "Date": d.timestamp.strftime("%Y-%m-%d"),
                "Time": d.timestamp.strftime("%H:%M:%S"),
                "Sci_Name": d.species.split(" (")[1][:-1] if " (" in d.species else "",
                "Confidence": d.confidence,
                "Lat": d.latitude,
                "Lon": d.longitude,
                "Cutoff": d.cutoff,
                "Week": d.week,
                "Sens": d.sensitivity,
                "Overlap": d.overlap,
            }
            for d in detections
        ]
        df = pd.DataFrame(data)
        df["DateTime"] = pd.to_datetime(df["DateTime"])
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
        current_week_stats = self.detection_manager.get_detection_counts_by_date_range(
            start_date, end_date
        )
        prior_week_stats = self.detection_manager.get_detection_counts_by_date_range(
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
        top_10_species_rows = self.detection_manager.get_top_species_with_prior_counts(
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
        new_species_rows = self.detection_manager.get_new_species_data(start_date, end_date)
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
        recent_detections = self.detection_manager.get_most_recent_detections(limit)
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

    def get_daily_detection_data_for_plotting(
        self, df: pd.DataFrame, resample_sel: str, specie: str
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare daily detection data for plotting."""
        config = DailyPlotConfig(resample_sel=resample_sel, specie=specie)
        return self.data_preparation_manager.prepare_daily_plot_data(df, config)
