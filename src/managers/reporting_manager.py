import datetime
import subprocess

from services.database_manager import DatabaseManager


class ReportingManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_weekly_report_data(self):
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

        # Get top 10 species for the current week with their counts from the prior week
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

        # Get new species for the current week
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

        # Disconnect from the database
        self.db_manager.disconnect()

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

    def get_most_recent_detections(self, limit: int = 10):
        self.db_manager.connect()
        query = "SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT ?"
        recent_detections = self.db_manager.fetch_all(query, (limit,))
        self.db_manager.disconnect()
        return recent_detections

    def generate_spectrogram(self, audio_file_path: str, output_image_path: str):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    audio_file_path,
                    "-lavfi",
                    "showspectrumpic=s=1280x720",  # Adjust size as needed
                    "-frames:v",
                    "1",
                    output_image_path,
                ],
                check=True,
            )
            print(f"Spectrogram generated successfully at {output_image_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error generating spectrogram: {e}")
        except FileNotFoundError:
            print("Error: ffmpeg command not found. Please ensure ffmpeg is installed.")
