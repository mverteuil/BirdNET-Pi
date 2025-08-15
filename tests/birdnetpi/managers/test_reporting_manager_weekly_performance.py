"""Performance and integration tests for weekly report functionality.

This test file focuses on performance, load testing, and complex integration scenarios
for the weekly report feature that are too expensive to run with the standard test suite.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.managers.reporting_manager import ReportingManager


@pytest.fixture
def data_manager():
    """Provide a mock DataManager instance for performance testing."""
    mock = MagicMock()
    mock.query_service = MagicMock()
    return mock


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    return MagicMock()


@pytest.fixture
def mock_location_service():
    """Provide a mock LocationService instance."""
    return MagicMock()


@pytest.fixture
def performance_reporting_manager(data_manager, path_resolver, mock_config, mock_location_service):
    """Provide a ReportingManager instance configured for performance testing."""
    from birdnetpi.managers.data_preparation_manager import DataPreparationManager
    from birdnetpi.managers.plotting_manager import PlottingManager

    mock_plotting_manager = MagicMock(spec=PlottingManager)
    mock_data_preparation_manager = MagicMock(spec=DataPreparationManager)

    manager = ReportingManager(
        data_manager=data_manager,
        path_resolver=path_resolver,
        config=mock_config,
        plotting_manager=mock_plotting_manager,
        data_preparation_manager=mock_data_preparation_manager,
        location_service=mock_location_service,
    )
    return manager


class TestWeeklyReportPerformance:
    """Test performance characteristics of weekly report functionality."""

    def test_get_weekly_report_data__large_dataset_performance(
        self, performance_reporting_manager, data_manager
    ):
        """Should handle large datasets efficiently without timeouts."""
        import time

        today = datetime.date(2025, 7, 12)

        # Simulate large dataset scenario
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        data_manager.get_all_detections.return_value = [mock_detection]

        # Mock large numbers that might be seen in production
        data_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 100000, "unique_species": 1500},  # Current week
            {"total_count": 85000, "unique_species": 1200},  # Prior week
        ]

        # Large top species list
        large_top_species = [
            {
                "scientific_name": f"Species_{i}",
                "common_name": f"Common Species {i}",
                "current_count": 5000 - i * 100,
                "prior_count": 4000 - i * 80,
            }
            for i in range(10)
        ]
        data_manager.get_top_species_with_prior_counts.return_value = large_top_species

        # Large new species list
        large_new_species = [{"species": f"New_Species_{i}", "count": 100 - i} for i in range(20)]
        data_manager.get_new_species_data.return_value = large_new_species

        with patch(
            "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
        ) as mock_date:
            mock_date.today.return_value = today

            # Measure execution time
            start_time = time.time()
            report_data = performance_reporting_manager.get_weekly_report_data()
            execution_time = time.time() - start_time

            # Performance assertions
            assert execution_time < 5.0  # Should complete within 5 seconds
            assert report_data["total_detections_current"] == 100000
            assert report_data["unique_species_current"] == 1500
            assert len(report_data["top_10_species"]) == 10
            assert len(report_data["new_species"]) == 20

    def test_get_weekly_report_data__concurrent_execution_safety(
        self, performance_reporting_manager, data_manager
    ):
        """Should be thread-safe for concurrent execution."""
        import concurrent.futures

        today = datetime.date(2025, 7, 12)

        # Setup consistent mock data
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        data_manager.get_all_detections.return_value = [mock_detection]

        data_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 1000, "unique_species": 50},
            {"total_count": 800, "unique_species": 40},
        ] * 10  # Enough for multiple concurrent calls

        data_manager.get_top_species_with_prior_counts.return_value = []
        data_manager.get_new_species_data.return_value = []

        def execute_weekly_report():
            """Execute weekly report data retrieval."""
            with patch(
                "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
            ) as mock_date:
                mock_date.today.return_value = today
                return performance_reporting_manager.get_weekly_report_data()

        # Execute concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(execute_weekly_report) for _ in range(5)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # All executions should succeed with consistent results
        assert len(results) == 5
        for result in results:
            assert result["total_detections_current"] == 1000
            assert result["unique_species_current"] == 50

    def test_get_weekly_report_data__memory_efficiency(
        self, performance_reporting_manager, data_manager
    ):
        """Should not accumulate excessive memory during execution."""
        import gc
        import os

        import psutil

        today = datetime.date(2025, 7, 12)

        # Get baseline memory usage
        process = psutil.Process(os.getpid())
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Setup mock data
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        data_manager.get_all_detections.return_value = [mock_detection]

        # Each iteration requires 2 calls (current + prior week), so 10 iterations need 20 values
        data_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 50000, "unique_species": 500},
            {"total_count": 45000, "unique_species": 450},
        ] * 10

        data_manager.get_top_species_with_prior_counts.return_value = []
        data_manager.get_new_species_data.return_value = []

        with patch(
            "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
        ) as mock_date:
            mock_date.today.return_value = today

            # Execute multiple times to check for memory leaks
            for _ in range(10):
                performance_reporting_manager.get_weekly_report_data()
                gc.collect()  # Force garbage collection

        # Check memory usage after execution
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - baseline_memory

        # Memory growth should be reasonable (less than 50MB for this test)
        assert memory_growth < 50, f"Memory grew by {memory_growth:.2f} MB"

    def test_percentage_calculation_precision_edge_cases(self, performance_reporting_manager):
        """Should handle extreme precision and edge cases in percentage calculations."""
        test_cases = [
            # (current, unique_current, prior, unique_prior, expected_total, expected_unique)
            (1, 1, 999999999, 999999, -100, -100),  # Extreme decrease
            (999999999, 999999, 1, 1, 99999999800, 99999800),  # Extreme increase
            (3, 3, 7, 7, -57, -57),  # Precision test
            (1000000000, 1000000000, 999999999, 999999999, 0, 0),  # Large numbers rounding
            (1, 1, 3, 3, -67, -67),  # One third reduction
        ]

        for (
            current_total,
            current_unique,
            prior_total,
            prior_unique,
            expected_total,
            expected_unique,
        ) in test_cases:
            result_total, result_unique = (
                performance_reporting_manager._calculate_percentage_differences(
                    current_total, current_unique, prior_total, prior_unique
                )
            )

            assert result_total == expected_total, f"Total: {result_total} != {expected_total}"
            assert result_unique == expected_unique, f"Unique: {result_unique} != {expected_unique}"

    def test_get_weekly_report_data__date_edge_cases_comprehensive(
        self, performance_reporting_manager, data_manager
    ):
        """Should handle comprehensive date edge cases and boundary conditions."""
        edge_case_dates = [
            # (today, latest_detection_date, expected_start, expected_end)
            # Find Monday at/before detection (or keep Sunday), end = that, start = end-6days
            (
                datetime.date(2025, 1, 1),
                datetime.date(2024, 12, 30),  # Monday (weekday 0)
                "2024-12-24",  # Tuesday (Monday 2024-12-30 - 6 days)
                "2024-12-30",  # Monday (the detection date itself)
            ),  # Year boundary
            (
                datetime.date(2025, 12, 31),
                datetime.date(2025, 12, 29),  # Sunday (weekday 6)
                "2025-12-23",  # Monday (Sunday 2025-12-29 - 6 days)
                "2025-12-29",  # Sunday (the latest detection date itself)
            ),  # End of year
            (
                datetime.date(2025, 2, 28),
                datetime.date(2025, 2, 23),  # Sunday (weekday 6)
                "2025-02-17",  # Monday (Sunday 2025-02-23 - 6 days)
                "2025-02-23",  # Sunday (the latest detection date itself)
            ),  # February
            (
                datetime.date(2024, 2, 29),
                datetime.date(2024, 2, 25),  # Sunday (weekday 6)
                "2024-02-19",  # Monday (Sunday 2024-02-25 - 6 days)
                "2024-02-25",  # Sunday (the latest detection date itself)
            ),  # Leap year
            (
                datetime.date(2025, 3, 1),
                datetime.date(2025, 2, 23),  # Sunday (weekday 6)
                "2025-02-17",  # Monday (Sunday 2025-02-23 - 6 days)
                "2025-02-23",  # Sunday (the latest detection date itself)
            ),  # Month boundary
        ]

        for today, latest_detection_date, expected_start, expected_end in edge_case_dates:
            # Setup mock detection with specific date
            mock_detection = MagicMock()
            mock_detection.timestamp = datetime.datetime.combine(
                latest_detection_date, datetime.time(12, 0, 0)
            )
            data_manager.get_all_detections.return_value = [mock_detection]

            data_manager.get_detection_counts_by_date_range.side_effect = [
                {"total_count": 10, "unique_species": 5},
                {"total_count": 8, "unique_species": 4},
            ]
            data_manager.get_top_species_with_prior_counts.return_value = []
            data_manager.get_new_species_data.return_value = []

            with patch(
                "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
            ) as mock_date:
                mock_date.today.return_value = today

                report_data = performance_reporting_manager.get_weekly_report_data()

                assert report_data["start_date"] == expected_start, (
                    f"Start date mismatch for {today}: "
                    f"{report_data['start_date']} != {expected_start}"
                )
                assert report_data["end_date"] == expected_end, (
                    f"End date mismatch for {today}: {report_data['end_date']} != {expected_end}"
                )

    def test_get_weekly_report_data__stress_test_multiple_scenarios(
        self, performance_reporting_manager, data_manager
    ):
        """Should handle stress testing with multiple rapid scenario changes."""
        import time

        scenarios = [
            # Scenario 1: High activity week
            {
                "current": {"total_count": 50000, "unique_species": 800},
                "prior": {"total_count": 30000, "unique_species": 600},
                "top_species_count": 10,
                "new_species_count": 15,
            },
            # Scenario 2: Low activity week
            {
                "current": {"total_count": 50, "unique_species": 8},
                "prior": {"total_count": 100, "unique_species": 12},
                "top_species_count": 5,
                "new_species_count": 1,
            },
            # Scenario 3: No prior data
            {
                "current": {"total_count": 1000, "unique_species": 50},
                "prior": {"total_count": 0, "unique_species": 0},
                "top_species_count": 8,
                "new_species_count": 10,
            },
        ]

        today = datetime.date(2025, 7, 12)
        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        data_manager.get_all_detections.return_value = [mock_detection]

        execution_times = []

        for scenario in scenarios:
            data_manager.get_detection_counts_by_date_range.side_effect = [
                scenario["current"],
                scenario["prior"],
            ]

            # Mock top species
            top_species = [
                {
                    "scientific_name": f"Species_{i}",
                    "common_name": f"Species {i}",
                    "current_count": 100 - i * 5,
                    "prior_count": 80 - i * 4,
                }
                for i in range(scenario["top_species_count"])
            ]
            data_manager.get_top_species_with_prior_counts.return_value = top_species

            # Mock new species
            new_species = [
                {"species": f"New_Species_{i}", "count": 20 - i}
                for i in range(scenario["new_species_count"])
            ]
            data_manager.get_new_species_data.return_value = new_species

            with patch(
                "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
            ) as mock_date:
                mock_date.today.return_value = today

                start_time = time.time()
                report_data = performance_reporting_manager.get_weekly_report_data()
                execution_time = time.time() - start_time
                execution_times.append(execution_time)

                # Verify correct data for each scenario
                assert report_data["total_detections_current"] == scenario["current"]["total_count"]
                assert (
                    report_data["unique_species_current"] == scenario["current"]["unique_species"]
                )
                assert len(report_data["top_10_species"]) == scenario["top_species_count"]
                assert len(report_data["new_species"]) == scenario["new_species_count"]

        # All scenarios should execute quickly and consistently
        max_execution_time = max(execution_times)
        avg_execution_time = sum(execution_times) / len(execution_times)

        assert max_execution_time < 2.0, f"Max execution time too high: {max_execution_time}"
        assert avg_execution_time < 1.0, f"Average execution time too high: {avg_execution_time}"


class TestWeeklyReportIntegration:
    """Integration tests that verify interaction between components."""

    def test_weekly_report_end_to_end_integration(
        self, performance_reporting_manager, data_manager
    ):
        """Should integrate all weekly report components correctly in realistic scenario."""
        today = datetime.date(2025, 7, 12)  # Saturday

        # Create realistic detection scenario
        detection_timestamps = [
            datetime.datetime(2025, 7, 8, 6, 30, 0),  # Tuesday morning
            datetime.datetime(2025, 7, 8, 7, 15, 0),  # Tuesday morning
            datetime.datetime(2025, 7, 9, 18, 45, 0),  # Wednesday evening
            datetime.datetime(2025, 7, 10, 5, 00, 0),  # Thursday dawn
            datetime.datetime(2025, 7, 11, 19, 30, 0),  # Friday evening
        ]

        mock_detections = []
        for ts in detection_timestamps:
            mock_detection = MagicMock()
            mock_detection.timestamp = ts
            mock_detections.append(mock_detection)

        data_manager.get_all_detections.return_value = mock_detections

        # Realistic detection counts
        data_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 156, "unique_species": 23},  # Current week
            {"total_count": 134, "unique_species": 19},  # Prior week
        ]

        # Realistic top species with various scenarios
        realistic_top_species = [
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "current_count": 35,
                "prior_count": 28,
            },
            {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "current_count": 22,
                "prior_count": 18,
            },
            {
                "scientific_name": "Cyanocitta cristata",
                "common_name": "Blue Jay",
                "current_count": 18,
                "prior_count": 0,
            },  # New in top 10
            {
                "scientific_name": "Poecile atricapillus",
                "common_name": "Black-capped Chickadee",
                "current_count": 15,
                "prior_count": 20,
            },  # Decreased
            {
                "scientific_name": "Sitta carolinensis",
                "common_name": "White-breasted Nuthatch",
                "current_count": 12,
                "prior_count": 12,
            },  # Same
        ]
        data_manager.get_top_species_with_prior_counts.return_value = realistic_top_species

        # Realistic new species
        realistic_new_species = [
            {"species": "Regulus calendula", "count": 7},  # Ruby-crowned Kinglet
            {"species": "Dendroica petechia", "count": 4},  # Yellow Warbler
        ]
        data_manager.get_new_species_data.return_value = realistic_new_species

        with patch(
            "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
        ) as mock_date:
            mock_date.today.return_value = today

            report_data = performance_reporting_manager.get_weekly_report_data()

            # Comprehensive integration verification
            assert (
                report_data["start_date"] == "2025-07-01"
            )  # Week containing latest detection (July 11 Friday -> Monday July 7 -> Week July 1-7)
            assert report_data["end_date"] == "2025-07-07"  # Monday of same week
            assert report_data["week_number"] == 27  # Correct ISO week number for July 1, 2025

            # Statistical verification
            assert report_data["total_detections_current"] == 156
            assert report_data["unique_species_current"] == 23
            assert report_data["percentage_diff_total"] == 16  # (156-134)/134 * 100 = 16.4 -> 16
            assert (
                report_data["percentage_diff_unique_species"] == 21
            )  # (23-19)/19 * 100 = 21.05 -> 21

            # Top species verification
            top_species = report_data["top_10_species"]
            assert len(top_species) == 5
            assert top_species[0]["common_name"] == "American Robin"
            assert top_species[0]["count"] == 35
            assert top_species[0]["percentage_diff"] == 25  # (35-28)/28 * 100 = 25

            assert top_species[2]["common_name"] == "Blue Jay"
            assert top_species[2]["percentage_diff"] == 0  # New species should have 0% diff

            assert top_species[3]["common_name"] == "Black-capped Chickadee"
            assert top_species[3]["percentage_diff"] == -25  # (15-20)/20 * 100 = -25

            assert top_species[4]["common_name"] == "White-breasted Nuthatch"
            assert top_species[4]["percentage_diff"] == 0  # Same count

            # New species verification
            new_species = report_data["new_species"]
            assert len(new_species) == 2
            assert new_species[0]["common_name"] == "Regulus calendula"
            assert new_species[0]["count"] == 7
            assert new_species[1]["common_name"] == "Dendroica petechia"
            assert new_species[1]["count"] == 4

    def test_weekly_report_database_interaction_patterns(
        self, performance_reporting_manager, data_manager
    ):
        """Should verify correct database interaction patterns and call sequences."""
        today = datetime.date(2025, 7, 12)

        mock_detection = MagicMock()
        mock_detection.timestamp = datetime.datetime(2025, 7, 10, 14, 30, 0)
        data_manager.get_all_detections.return_value = [mock_detection]

        data_manager.get_detection_counts_by_date_range.side_effect = [
            {"total_count": 100, "unique_species": 15},
            {"total_count": 80, "unique_species": 12},
        ]

        data_manager.get_top_species_with_prior_counts.return_value = [
            {
                "scientific_name": "Test species",
                "common_name": "Test Species",
                "current_count": 10,
                "prior_count": 8,
            }
        ]

        data_manager.get_new_species_data.return_value = [
            {"species": "New test species", "count": 5}
        ]

        with patch(
            "birdnetpi.managers.reporting_manager.datetime.date", wraps=datetime.date
        ) as mock_date:
            mock_date.today.return_value = today

            performance_reporting_manager.get_weekly_report_data()

            # Verify correct call sequence and parameters
            data_manager.get_all_detections.assert_called_once()

            # Verify date range calls with correct parameters
            calls = data_manager.get_detection_counts_by_date_range.call_args_list
            assert len(calls) == 2

            # Current week call (based on detection date July 10 -> Monday July 7 -> Week July 1-7)
            current_start, current_end = calls[0][0]
            assert current_start == datetime.datetime(2025, 7, 1, 0, 0, 0)
            assert current_end == datetime.datetime(2025, 7, 7, 23, 59, 59, 999999)

            # Prior week call
            prior_start, prior_end = calls[1][0]
            assert prior_start == datetime.datetime(2025, 6, 24, 0, 0, 0)
            assert prior_end == datetime.datetime(2025, 6, 30, 23, 59, 59, 999999)

            # Verify top species call
            top_species_call = data_manager.get_top_species_with_prior_counts.call_args
            assert top_species_call[0][0] == datetime.datetime(2025, 7, 1, 0, 0, 0)
            assert top_species_call[0][1] == datetime.datetime(2025, 7, 7, 23, 59, 59, 999999)
            assert top_species_call[0][2] == datetime.datetime(2025, 6, 24, 0, 0, 0)
            assert top_species_call[0][3] == datetime.datetime(2025, 6, 30, 23, 59, 59, 999999)

            # Verify new species call
            new_species_call = data_manager.get_new_species_data.call_args
            assert new_species_call[0][0] == datetime.datetime(2025, 7, 1, 0, 0, 0)
            assert new_species_call[0][1] == datetime.datetime(2025, 7, 7, 23, 59, 59, 999999)
