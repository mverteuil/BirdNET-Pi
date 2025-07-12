import datetime

from BirdNET_Pi.src.services.database_manager import DatabaseManager


class ReportingManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_weekly_report(self):
        today = datetime.date.today()
        # Calculate last Sunday (end of last week)
        last_sunday = today - datetime.timedelta(days=today.weekday() + 1)
        # Calculate start of last week (Monday before last Sunday)
        start_date = last_sunday - datetime.timedelta(days=6)
        end_date = last_sunday

        # Calculate dates for the prior week
        prior_start_date = start_date - datetime.timedelta(days=7)
        prior_end_date = end_date - datetime.timedelta(days=7)

        # Connect to the database
        self.db_manager.connect()

        # Total Detections and Unique Species for the current week
        current_week_detections_query = """
            SELECT Com_Name, COUNT(*) as count
            FROM detections
            WHERE Date BETWEEN ? AND ?
            GROUP BY Com_Name
            ORDER BY count DESC
        """
        current_week_total_detections_query = """
            SELECT COUNT(*) as total_count
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        current_week_unique_species_query = """
            SELECT COUNT(DISTINCT Com_Name) as unique_species_count
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """

        current_week_detections = self.db_manager.fetch_all(
            current_week_detections_query, (str(start_date), str(end_date))
        )
        current_week_total_count = self.db_manager.fetch_one(
            current_week_total_detections_query, (str(start_date), str(end_date))
        )
        current_week_unique_species_count = self.db_manager.fetch_one(
            current_week_unique_species_query, (str(start_date), str(end_date))
        )

        # Total Detections and Unique Species for the prior week
        prior_week_total_detections_query = """
            SELECT COUNT(*) as total_count
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        prior_week_unique_species_query = """
            SELECT COUNT(DISTINCT Com_Name) as unique_species_count
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """

        prior_week_total_count = self.db_manager.fetch_one(
            prior_week_total_detections_query,
            (str(prior_start_date), str(prior_end_date)),
        )
        prior_week_unique_species_count = self.db_manager.fetch_one(
            prior_week_unique_species_query,
            (str(prior_start_date), str(prior_end_date)),
        )

        # Disconnect from the database
        self.db_manager.disconnect()

        # Extract counts
        total_detections_current = (
            current_week_total_count["total_count"] if current_week_total_count else 0
        )
        unique_species_current = (
            current_week_unique_species_count["unique_species_count"]
            if current_week_unique_species_count
            else 0
        )
        total_detections_prior = (
            prior_week_total_count["total_count"] if prior_week_total_count else 0
        )
        unique_species_prior = (
            prior_week_unique_species_count["unique_species_count"]
            if prior_week_unique_species_count
            else 0
        )

        # Calculate percentage differences
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

        # Prepare top 10 species data
        top_10_species = []
        for i, detection in enumerate(current_week_detections):
            if i >= 10:
                break
            com_name = detection["Com_Name"]
            current_count = detection["count"]

            prior_week_species_count_query = """
                SELECT COUNT(*) as count
                FROM detections
                WHERE Com_Name = ? AND Date BETWEEN ? AND ?
            """
            prior_count_row = self.db_manager.fetch_one(
                prior_week_species_count_query,
                (com_name, str(prior_start_date), str(prior_end_date)),
            )
            prior_count = prior_count_row["count"] if prior_count_row else 0

            species_percentage_diff = 0
            if prior_count > 0:
                species_percentage_diff = round(
                    ((current_count - prior_count) / prior_count) * 100
                )

            top_10_species.append(
                {
                    "com_name": com_name,
                    "count": current_count,
                    "percentage_diff": species_percentage_diff,
                }
            )

        # Prepare new species data
        new_species = []
        for detection in current_week_detections:
            com_name = detection["Com_Name"]
            current_count = detection["count"]

            # Check if this species was detected in any other week (not current week)
            other_weeks_query = """
                SELECT COUNT(*) as count
                FROM detections
                WHERE Com_Name = ? AND Date NOT BETWEEN ? AND ?
            """
            other_weeks_count_row = self.db_manager.fetch_one(
                other_weeks_query, (com_name, str(start_date), str(end_date))
            )
            other_weeks_count = (
                other_weeks_count_row["count"] if other_weeks_count_row else 0
            )

            if other_weeks_count == 0:
                new_species.append({"com_name": com_name, "count": current_count})

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "week_number": end_date.isocalendar()[1],
            "total_detections_current": total_detections_current,
            "percentage_diff_total": percentage_diff_total,
            "unique_species_current": unique_species_current,
            "percentage_diff_unique_species": percentage_diff_unique_species,
            "top_10_species": top_10_species,
            "new_species": new_species,
            "prior_week_number": prior_end_date.isocalendar()[1],
        }
