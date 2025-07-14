import datetime
from unittest.mock import MagicMock, patch

import pytest

from managers.plotting_manager import PlottingManager
from managers.reporting_manager import ReportingManager


@pytest.fixture
def mock_plotting_manager():
    """Provide a mock PlottingManager instance."""
    return MagicMock(spec=PlottingManager)


@pytest.fixture
def db_manager():
    """Provide a mock DatabaseManager instance."""
    return MagicMock()


@pytest.fixture
def reporting_manager(db_manager, file_path_resolver, mock_plotting_manager):
    """Provide a ReportingManager instance with mocked dependencies."""
    return ReportingManager(db_manager, file_path_resolver)


def test_get_most_recent_detections(reporting_manager, db_manager):
    """Should return a list of recent detections."""
    db_manager.get_most_recent_detections.return_value = [
        {"com_name": "American Robin", "Date": "2025-07-12", "Time": "10:00:00"},
        {"com_name": "Northern Cardinal", "Date": "2025-07-12", "Time": "09:59:00"},
    ]

    recent_detections = reporting_manager.get_most_recent_detections(limit=2)

    assert len(recent_detections) == 2
    assert recent_detections[0]["com_name"] == "American Robin"
    db_manager.get_most_recent_detections.assert_called_once_with(2)


def test_get_weekly_report_data(reporting_manager, db_manager):
    """Should return a dictionary of weekly report data."""
    today = datetime.date(2025, 7, 12)  # Saturday
    with patch(
        "managers.reporting_manager.datetime.date", wraps=datetime.date
    ) as mock_date:
        mock_date.today.return_value = today

        db_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 100, "unique_species": 10},  # Current week stats
            {"total_count": 80, "unique_species": 8},  # Prior week stats
        ]

        db_manager.get_top_species_with_prior_counts.return_value = [
            {
                "com_name": "American Robin",
                "current_count": 20,
                "prior_count": 15,
            },
            {
                "com_name": "Northern Cardinal",
                "current_count": 15,
                "prior_count": 10,
            },
        ]

        db_manager.get_new_species_data.return_value = [
            {"com_name": "Blue Jay", "count": 5}
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

        # Assertions for db_manager method calls
        # Extract the actual calls made to get_detection_counts_by_date_range
        calls = db_manager.get_detection_counts_by_date_range.call_args_list

        # Assert the first call
        assert calls[0].args[0] == datetime.date(2025, 6, 30)
        assert calls[0].args[1] == datetime.date(2025, 7, 6)

        # Assert the second call
        assert calls[1].args[0] == datetime.date(2025, 6, 23)
        assert calls[1].args[1] == datetime.date(2025, 6, 29)

        db_manager.get_top_species_with_prior_counts.assert_called_once_with(
            datetime.date(2025, 6, 30),
            datetime.date(2025, 7, 6),
            datetime.date(2025, 6, 23),
            datetime.date(2025, 6, 29),
        )
        db_manager.get_new_species_data.assert_called_once_with(
            datetime.date(2025, 6, 30), datetime.date(2025, 7, 6)
        )
