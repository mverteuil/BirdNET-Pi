import datetime

import pandas as pd

from managers.database_manager import DatabaseManager
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver


class ReportingManager:
    def __init__(
        self, db_manager: DatabaseManager, file_path_resolver: FilePathResolver
    ):
        self.db_manager = db_manager
        self.file_path_resolver = file_path_resolver
        self.config = ConfigFileParser(
            self.file_path_resolver.get_birdnet_pi_config_path()
        ).load_config()

    def get_data(self):
        df = self.db_manager.get_all_detections()
        df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
        df = df.set_index("DateTime")
        return df

    def _get_weekly_stats(self, start_date, end_date, prior_start_date, prior_end_date):
        """Fetches total detection counts and unique species counts for the current and prior weeks.

        Args:
            start_date (datetime.date): Start date of the current week.
            end_date (datetime.date): End date of the current week.
            prior_start_date (datetime.date): Start date of the prior week.
            prior_end_date (datetime.date): End date of the prior week.

        Returns:
            tuple: A tuple containing (current_week_stats, prior_week_stats) dictionaries.
        """
        # Connect to the database
        self.db_manager.connect()

        # Get stats for the current week
        current_week_stats_query = """
            SELECT COUNT(*) as total_count, COUNT(DISTINCT Com_Name) as unique_species
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        current_week_stats = self.db_manager.fetch_one(
            current_week_stats_query, (str(start_date), str(end_date))
        )

        # Get stats for the prior week
        prior_week_stats_query = """
            SELECT COUNT(*) as total_count, COUNT(DISTINCT Com_Name) as unique_species
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        prior_week_stats = self.db_manager.fetch_one(
            prior_week_stats_query, (str(prior_start_date), str(prior_end_date))
        )
        self.db_manager.disconnect()
        return current_week_stats, prior_week_stats

    def _get_top_species_data(
        self, start_date, end_date, prior_start_date, prior_end_date
    ):
        """Fetches the top 10 species for the current week and their counts from the prior week.

        Args:
            start_date (datetime.date): Start date of the current week.
            end_date (datetime.date): End date of the current week.
            prior_start_date (datetime.date): Start date of the prior week.
            prior_end_date (datetime.date): End date of the prior week.

        Returns:
            list: A list of dictionaries, each containing species common name, current count, and percentage difference from the prior week.
        """
        top_species_query = """
        WITH CurrentWeekCounts AS (
            SELECT Com_Name, COUNT(*) as count
            FROM detections
            WHERE Date BETWEEN ? AND ?
            GROUP BY Com_Name
        ),
        PriorWeekCounts AS (
            SELECT Com_Name, COUNT(*) as count
            FROM detections
            WHERE Date BETWEEN ? AND ?
            GROUP BY Com_Name
        )
        SELECT
            c.Com_Name,
            c.count as current_count,
            COALESCE(p.count, 0) as prior_count
        FROM CurrentWeekCounts c
        LEFT JOIN PriorWeekCounts p ON c.Com_Name = p.Com_Name
        ORDER BY current_count DESC
        LIMIT 10
        """
        top_10_species_rows = self.db_manager.fetch_all(
            top_species_query,
            (
                str(start_date),
                str(end_date),
                str(prior_start_date),
                str(prior_end_date),
            ),
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
                        "com_name": row["Com_Name"],
                        "count": current_count,
                        "percentage_diff": percentage_diff,
                    }
                )
        return top_10_species

    def _get_new_species_data(self, start_date, end_date):
        """Fetches new species detected in the current week that were not present in prior data.

        Args:
            start_date (datetime.date): Start date of the current week.
            end_date (datetime.date): End date of the current week.

        Returns:
            list: A list of dictionaries, each containing new species common name and count.
        """
        new_species_query = """
        SELECT Com_Name, COUNT(*) as count
        FROM detections
        WHERE Date BETWEEN ? AND ?
          AND Com_Name NOT IN (
            SELECT DISTINCT Com_Name
            FROM detections
            WHERE Date < ?
          )
        GROUP BY Com_Name
        ORDER BY count DESC
        """
        new_species_rows = self.db_manager.fetch_all(
            new_species_query, (str(start_date), str(end_date), str(start_date))
        )
        new_species = (
            [
                {"com_name": row["Com_Name"], "count": row["count"]}
                for row in new_species_rows
            ]
            if new_species_rows
            else []
        )
        return new_species

    def _calculate_percentage_differences(
        self,
        total_detections_current,
        unique_species_current,
        total_detections_prior,
        unique_species_prior,
    ):
        """Calculates percentage differences for total detections and unique species.

        Args:
            total_detections_current (int): Total detections in the current period.
            unique_species_current (int): Unique species in the current period.
            total_detections_prior (int): Total detections in the prior period.
            unique_species_prior (int): Unique species in the prior period.

        Returns:
            tuple: A tuple containing (percentage_diff_total, percentage_diff_unique_species).
        """
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

    def get_weekly_report_data(self):
        """Retrieves and processes data for the weekly report.

        This method calculates detection statistics for the current and prior weeks,
        identifies top species, and finds new species.

        Returns:
            dict: A dictionary containing weekly report data, including total detections,
                  unique species, percentage differences, top 10 species, and new species.
        """
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

    def _prepare_sunrise_sunset_data_for_plot(self, num_days_to_display, fig_x):
        """Prepares sunrise and sunset data for plotting.

        Args:
            num_days_to_display (int): Number of days to display data for.
            fig_x (list): Formatted dates for plotting.

        Returns:
            tuple: A tuple containing:
                - sunrise_week_list (list): List of days for sunrise data.
                - sunrise_list (list): List of sunrise times.
                - sunrise_text_list (list): List of sunrise text labels.
                - daysback_range (list): Range of days for plotting.
        """
        sunrise_week_list, sunrise_list, sunrise_text_list = (
            self.get_sunrise_sunset_data(num_days_to_display)
        )
        daysback_range = fig_x
        daysback_range.append(None)
        daysback_range.extend(daysback_range)
        daysback_range = daysback_range[:-1]
        return sunrise_week_list, sunrise_list, sunrise_text_list, daysback_range

    def get_most_recent_detections(self, limit: int = 10):
        self.db_manager.connect()
        query = "SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT ?"
        recent_detections = self.db_manager.fetch_all(query, (limit,))
        self.db_manager.disconnect()
        return recent_detections
