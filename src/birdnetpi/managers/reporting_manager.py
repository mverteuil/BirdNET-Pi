import datetime
from typing import Any, cast

import pandas as pd

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.models.config import BirdNETConfig, DailyPlotConfig
from birdnetpi.services.location_service import LocationService
from birdnetpi.utils.file_path_resolver import FilePathResolver


class ReportingManager:
    """Manages data retrieval, processing, and reporting functionalities."""

    def __init__(
        self,
        detection_manager: DetectionManager,
        file_path_resolver: FilePathResolver,
        config: BirdNETConfig,
        plotting_manager: PlottingManager,
        data_preparation_manager: DataPreparationManager,
        location_service: LocationService,
    ) -> None:
        self.detection_manager = detection_manager
        self.file_path_resolver = file_path_resolver
        self.config = config
        self.plotting_manager = plotting_manager
        self.data_preparation_manager = data_preparation_manager
        self.location_service = location_service

    def get_data(self, use_ioc_data: bool = True, language_code: str = "en") -> pd.DataFrame:
        """Retrieve all detection data from the database and format it into a DataFrame.

        Args:
            use_ioc_data: Whether to use IOC taxonomic data for enriched information
            language_code: Language for IOC translations
        """
        if use_ioc_data and self.detection_manager.detection_query_service:
            try:
                # Get detections with IOC data (all detections, no limit)
                detections_with_ioc = (
                    self.detection_manager.detection_query_service.get_detections_with_ioc_data(
                        limit=10000,  # Large limit to get all data
                        language_code=language_code,
                    )
                )
                data = [
                    {
                        "common_name": d.get_best_common_name(prefer_translation=True),
                        "datetime": d.timestamp,
                        "date": d.timestamp.strftime("%Y-%m-%d"),
                        "time": d.timestamp.strftime("%H:%M:%S"),
                        "scientific_name": d.scientific_name or "",
                        "confidence": d.confidence,
                        "latitude": d.detection.latitude,
                        "longitude": d.detection.longitude,
                        "species_confidence_threshold": d.detection.species_confidence_threshold,
                        "week": d.detection.week,
                        "sensitivity_setting": d.detection.sensitivity_setting,
                        "overlap": d.detection.overlap,
                        "ioc_english_name": d.ioc_english_name,
                        "translated_name": d.translated_name,
                        "family": d.family,
                        "genus": d.genus,
                        "order_name": d.order_name,
                    }
                    for d in detections_with_ioc
                ]
            except Exception as e:
                print(f"Error retrieving IOC data, falling back to regular detections: {e}")
                # Fall back to regular detection data
                use_ioc_data = False

        if not use_ioc_data:
            # Original implementation without IOC data
            detections = self.detection_manager.get_all_detections()
            data = [
                {
                    "common_name": d.common_name or "",
                    "datetime": d.timestamp,
                    "date": d.timestamp.strftime("%Y-%m-%d"),
                    "time": d.timestamp.strftime("%H:%M:%S"),
                    "scientific_name": d.scientific_name or "",
                    "confidence": d.confidence,
                    "latitude": d.latitude,
                    "longitude": d.longitude,
                    "species_confidence_threshold": d.species_confidence_threshold,
                    "week": d.week,
                    "sensitivity_setting": d.sensitivity_setting,
                    "overlap": d.overlap,
                }
                for d in detections
            ]
        df = pd.DataFrame(data)
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime")
        else:
            # Create empty DataFrame with expected columns when no data
            column_names = [
                "common_name",
                "datetime",
                "date",
                "time",
                "scientific_name",
                "confidence",
                "latitude",
                "longitude",
                "species_confidence_threshold",
                "week",
                "sensitivity_setting",
                "overlap",
            ]
            df = pd.DataFrame({col: [] for col in column_names})
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime")
        return df

    def _get_weekly_stats(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        prior_start_date: datetime.date,
        prior_end_date: datetime.date,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Get total detection counts and unique species counts for the current and prior weeks."""
        current_week_stats = self.detection_manager.get_detection_counts_by_date_range(
            datetime.datetime.combine(start_date, datetime.time.min),
            datetime.datetime.combine(end_date, datetime.time.max),
        )
        prior_week_stats = self.detection_manager.get_detection_counts_by_date_range(
            datetime.datetime.combine(prior_start_date, datetime.time.min),
            datetime.datetime.combine(prior_end_date, datetime.time.max),
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
            datetime.datetime.combine(start_date, datetime.time.min),
            datetime.datetime.combine(end_date, datetime.time.max),
            datetime.datetime.combine(prior_start_date, datetime.time.min),
            datetime.datetime.combine(prior_end_date, datetime.time.max),
        )

        top_10_species = []
        if top_10_species_rows:
            for row in top_10_species_rows:
                current_count = row["current_count"]
                prior_count = row["prior_count"]
                percentage_diff = 0
                if prior_count > 0:
                    percentage_diff = round(((current_count - prior_count) / prior_count) * 100)

                top_10_species.append(
                    {
                        "common_name": row["common_name"],
                        "count": current_count,
                        "percentage_diff": percentage_diff,
                    }
                )
        return top_10_species

    def _get_new_species_data(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[dict[str, Any]]:
        """Fetch new species detected in the current week that were not present in prior data."""
        new_species_rows = self.detection_manager.get_new_species_data(
            datetime.datetime.combine(start_date, datetime.time.min),
            datetime.datetime.combine(end_date, datetime.time.max),
        )
        new_species = (
            [{"common_name": row["species"], "count": row["count"]} for row in new_species_rows]
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
                ((total_detections_current - total_detections_prior) / total_detections_prior) * 100
            )

        percentage_diff_unique_species = 0
        if unique_species_prior > 0:
            percentage_diff_unique_species = round(
                ((unique_species_current - unique_species_prior) / unique_species_prior) * 100
            )
        return percentage_diff_total, percentage_diff_unique_species

    def get_weekly_report_data(self) -> dict[str, Any]:
        """Retrieve and process data for the weekly report."""
        today = datetime.date.today()

        # Check if we have data for the current period
        all_detections = self.detection_manager.get_all_detections()

        if all_detections:
            # Get the date range of available data
            detection_dates = [
                (d.timestamp).date()
                for d in all_detections
                if (d.timestamp) is not None and isinstance((d.timestamp), datetime.datetime)
            ]
            if detection_dates:
                # Use the most recent week with data
                latest_date = max(detection_dates)
                # Find the Sunday at or before the latest date
                last_sunday = latest_date - datetime.timedelta(days=latest_date.weekday())
                if latest_date.weekday() == 6:  # If latest_date is Sunday
                    last_sunday = latest_date
                start_date = last_sunday - datetime.timedelta(days=6)
                end_date = last_sunday
            else:
                # Fallback to original logic if no valid dates
                last_sunday = today - datetime.timedelta(days=today.weekday() + 1)
                start_date = last_sunday - datetime.timedelta(days=6)
                end_date = last_sunday
        else:
            # Original logic when no data
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
        total_detections_current = current_week_stats["total_count"] if current_week_stats else 0
        unique_species_current = current_week_stats["unique_species"] if current_week_stats else 0
        total_detections_prior = prior_week_stats["total_count"] if prior_week_stats else 0
        unique_species_prior = prior_week_stats["unique_species"] if prior_week_stats else 0

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

    def get_most_recent_detections(
        self, limit: int = 10, language_code: str = "en", use_ioc_data: bool = True
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent detection records from the database.

        Args:
            limit: Maximum number of detections to return
            language_code: Language for IOC translations
            use_ioc_data: Whether to include IOC taxonomic data
        """
        if use_ioc_data and self.detection_manager.detection_query_service:
            try:
                return self.detection_manager.get_most_recent_detections_with_ioc(
                    limit, language_code
                )
            except Exception as e:
                print(f"Error getting recent detections with IOC data, falling back: {e}")

        # Fallback to original method
        recent_detections = self.detection_manager.get_most_recent_detections(limit)
        return recent_detections

    def get_todays_detections(
        self, language_code: str = "en", use_ioc_data: bool = True
    ) -> list[dict[str, Any]]:
        """Retrieve all detection records from the database for the current day.

        Args:
            language_code: Language for IOC translations
            use_ioc_data: Whether to include IOC taxonomic data
        """
        today = datetime.date.today()
        start_datetime = datetime.datetime.combine(today, datetime.time.min)
        end_datetime = datetime.datetime.combine(today, datetime.time.max)

        # Try to use IOC-enhanced data if available
        if use_ioc_data and self.detection_manager.detection_query_service:
            try:
                detections_with_ioc = (
                    self.detection_manager.detection_query_service.get_detections_with_ioc_data(
                        limit=1000, since=start_datetime, language_code=language_code
                    )
                )

                # Filter for today's detections
                todays_detections = [
                    d for d in detections_with_ioc if start_datetime <= d.timestamp <= end_datetime
                ]

                # If no detections for today, get the most recent day's detections
                if not todays_detections and detections_with_ioc:
                    # Find the most recent date with detections
                    detection_dates = [d.timestamp.date() for d in detections_with_ioc]
                    if detection_dates:
                        latest_date = max(detection_dates)
                        start_datetime = datetime.datetime.combine(latest_date, datetime.time.min)
                        end_datetime = datetime.datetime.combine(latest_date, datetime.time.max)
                        todays_detections = [
                            d
                            for d in detections_with_ioc
                            if start_datetime <= d.timestamp <= end_datetime
                        ]

                # Convert DetectionWithIOCData objects to dictionaries
                return [
                    {
                        "date": d.timestamp.strftime("%Y-%m-%d"),
                        "time": d.timestamp.strftime("%H:%M:%S"),
                        "scientific_name": d.scientific_name or "",
                        "common_name": d.get_best_common_name(prefer_translation=True),
                        "confidence": d.confidence or 0,
                        "latitude": d.detection.latitude or "",
                        "longitude": d.detection.longitude or "",
                        "ioc_english_name": d.ioc_english_name,
                        "translated_name": d.translated_name,
                        "family": d.family,
                        "genus": d.genus,
                        "order_name": d.order_name,
                    }
                    for d in todays_detections
                ]
            except Exception as e:
                print(f"Error getting today's detections with IOC data, falling back: {e}")
                # Force fallback to regular detection method
                use_ioc_data = False

        # Fallback to original implementation
        all_detections = self.detection_manager.get_all_detections()
        todays_detections = [
            d
            for d in all_detections
            if isinstance(d.timestamp, datetime.datetime)
            and start_datetime <= d.timestamp <= end_datetime
        ]

        # If no detections for today, get the most recent day's detections for demo purposes
        if not todays_detections and all_detections:
            # Find the most recent date with detections
            valid_detections = [
                d for d in all_detections 
                if isinstance(d.timestamp, datetime.datetime)
            ]
            if valid_detections:
                latest_date = max(
                    cast(datetime.datetime, d.timestamp).date()
                    for d in valid_detections
                )
                start_datetime = datetime.datetime.combine(latest_date, datetime.time.min)
                end_datetime = datetime.datetime.combine(latest_date, datetime.time.max)
                todays_detections = [
                    d
                    for d in all_detections
                    if isinstance(d.timestamp, datetime.datetime)
                    and start_datetime <= d.timestamp <= end_datetime
                ]

        # Convert Detection objects to dictionaries matching the template expectations
        return [
            {
                "date": d.timestamp.strftime("%Y-%m-%d") if d.timestamp else "",
                "time": d.timestamp.strftime("%H:%M:%S") if d.timestamp else "",
                "scientific_name": d.scientific_name or "",
                "common_name": d.common_name or "",
                "confidence": d.confidence or 0,
                "latitude": d.latitude or "",
                "longitude": d.longitude or "",
            }
            for d in todays_detections
        ]

    def date_filter(self, df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        """Filter a DataFrame by date range."""
        filt = (df.index >= pd.Timestamp(start_date)) & (
            df.index <= pd.Timestamp(end_date) + datetime.timedelta(days=1)
        )
        filtered_df = df[filt]
        # Ensure we return a DataFrame, not a Series
        if isinstance(filtered_df, pd.Series):
            return filtered_df.to_frame()
        return filtered_df

    def get_daily_detection_data_for_plotting(
        self, df: pd.DataFrame, resample_sel: str, species: str
    ) -> tuple[pd.DataFrame, list[str], list[float], list[str]]:
        """Prepare daily detection data for plotting."""
        config = DailyPlotConfig(resample_sel=resample_sel, species=species)
        return self.data_preparation_manager.prepare_daily_plot_data(df, config)

    def get_best_detections(self, limit: int = 20) -> list[dict]:
        """Retrieve the best detections from the database."""
        best_detections = self.detection_manager.get_best_detections(limit)
        return best_detections
