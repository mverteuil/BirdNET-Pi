import datetime
import unittest
from unittest.mock import MagicMock

from managers.reporting_manager import ReportingManager


class TestReportingManager(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock()
        self.reporting_manager = ReportingManager(self.db_manager)

    def test_get_most_recent_detections(self):
        # Should return a list of recent detections
        self.db_manager.fetch_all.return_value = [
            {"Com_Name": "American Robin", "Date": "2025-07-12", "Time": "10:00:00"},
            {"Com_Name": "Northern Cardinal", "Date": "2025-07-12", "Time": "09:59:00"},
        ]

        recent_detections = self.reporting_manager.get_most_recent_detections(limit=2)

        self.assertEqual(len(recent_detections), 2)
        self.assertEqual(recent_detections[0]["Com_Name"], "American Robin")
        self.db_manager.connect.assert_called_once()
        self.db_manager.fetch_all.assert_called_once_with(
            "SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT ?", (2,)
        )
        self.db_manager.disconnect.assert_called_once()

    def test_get_weekly_report_data(self):
        # Should return a dictionary of weekly report data
        today = datetime.date(2025, 7, 12)  # Saturday
        with unittest.mock.patch(
            "managers.reporting_manager.datetime.date"
        ) as mock_date:
            mock_date.today.return_value = today

            self.db_manager.fetch_one.side_effect = [
                {"total_count": 100, "unique_species": 10},
                {"total_count": 80, "unique_species": 8},
            ]

            self.db_manager.fetch_all.side_effect = [
                [
                    {
                        "Com_Name": "American Robin",
                        "current_count": 20,
                        "prior_count": 15,
                    },
                    {
                        "Com_Name": "Northern Cardinal",
                        "current_count": 15,
                        "prior_count": 10,
                    },
                ],
                [{"Com_Name": "Blue Jay", "count": 5}],
            ]

            report_data = self.reporting_manager.get_weekly_report_data()

            self.assertEqual(report_data["start_date"], "2025-06-30")
            self.assertEqual(report_data["end_date"], "2025-07-06")
            self.assertEqual(report_data["week_number"], 27)
            self.assertEqual(report_data["total_detections_current"], 100)
            self.assertEqual(report_data["percentage_diff_total"], 25)
            self.assertEqual(report_data["unique_species_current"], 10)
            self.assertEqual(report_data["percentage_diff_unique_species"], 25)
            self.assertEqual(len(report_data["top_10_species"]), 2)
            self.assertEqual(
                report_data["top_10_species"][0]["com_name"], "American Robin"
            )
            self.assertEqual(report_data["top_10_species"][0]["percentage_diff"], 33)
            self.assertEqual(len(report_data["new_species"]), 1)
            self.assertEqual(report_data["new_species"][0]["com_name"], "Blue Jay")


if __name__ == "__main__":
    unittest.main()
