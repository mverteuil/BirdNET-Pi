import datetime
from unittest.mock import MagicMock, patch

import pytest

from managers.reporting_manager import ReportingManager


@pytest.fixture
def db_manager():
    return MagicMock()


@pytest.fixture
def reporting_manager(db_manager, file_path_resolver):
    return ReportingManager(db_manager, file_path_resolver)


def test_get_most_recent_detections(reporting_manager, db_manager):
    """Should return a list of recent detections."""
    db_manager.fetch_all.return_value = [
        {"Com_Name": "American Robin", "Date": "2025-07-12", "Time": "10:00:00"},
        {"Com_Name": "Northern Cardinal", "Date": "2025-07-12", "Time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["Com_Name"] == "American Robin"
    db_manager.connect.assert_called_once()
    db_manager.fetch_all.assert_called_once_with(
        "SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT ?", (2,)
    )
    db_manager.disconnect.assert_called_once()


def test_get_weekly_report_data(reporting_manager, db_manager):
    """Should return a dictionary of weekly report data."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch("managers.reporting_manager.datetime.date") as mock_date:
        mock_date.today.return_value = today

        db_manager.fetch_one.side_effect = [
            {"total_count": 100, "unique_species": 10},
            {"total_count": 80, "unique_species": 8},
        ]

        db_manager.fetch_all.side_effect = [
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

        report_data = reporting_manager.get_weekly_report_data()

        assert report_data["start_date"] == "2025-06-30"
        assert report_data["end_date"] == "2025-07-06"
        assert report_data["week_number"] == 27
        assert report_data["total_detections_current"] == 100
        assert report_data["percentage_diff_total"] == 25
        assert report_data["unique_species_current"] == 10
        assert report_data["percentage_diff_unique_species"] == 25
        assert len(report_data["top_10_species"]) == 2
        assert report_data["top_10_species"][0]["com_name"] == "American Robin"
        assert report_data["top_10_species"][0]["percentage_diff"] == 33
        assert len(report_data["new_species"]) == 1
        assert report_data["new_species"][0]["com_name"] == "Blue Jay"
