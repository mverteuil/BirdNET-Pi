"""Tests for detection statistics display in PresentationManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.detections.queries import DetectionQueryService


class TestDetectionStatistics:
    """Test detection statistics calculation and display."""

    @pytest.fixture
    def mock_analytics_manager(self):
        """Create mock analytics manager."""
        mock = MagicMock(
            spec=AnalyticsManager,
            get_temporal_patterns=AsyncMock(
                spec=AnalyticsManager.get_temporal_patterns,
                return_value={
                    "hourly_distribution": [
                        0,
                        5,
                        10,
                        15,
                        20,
                        25,
                        30,
                        35,
                        40,
                        35,
                        30,
                        25,
                        20,
                        15,
                        10,
                        5,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "peak_hour": 8,
                    "periods": {},
                },
            ),
            get_weekly_patterns=AsyncMock(
                spec=AnalyticsManager.get_weekly_patterns,
                return_value={
                    "sun": [
                        10,
                        15,
                        20,
                        25,
                        30,
                        35,
                        40,
                        45,
                        50,
                        45,
                        40,
                        35,
                        30,
                        25,
                        20,
                        15,
                        10,
                        5,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "mon": [
                        12,
                        17,
                        22,
                        27,
                        32,
                        37,
                        42,
                        47,
                        52,
                        47,
                        42,
                        37,
                        32,
                        27,
                        22,
                        17,
                        12,
                        7,
                        2,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "tue": [
                        14,
                        19,
                        24,
                        29,
                        34,
                        39,
                        44,
                        49,
                        54,
                        49,
                        44,
                        39,
                        34,
                        29,
                        24,
                        19,
                        14,
                        9,
                        4,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "wed": [
                        16,
                        21,
                        26,
                        31,
                        36,
                        41,
                        46,
                        51,
                        56,
                        51,
                        46,
                        41,
                        36,
                        31,
                        26,
                        21,
                        16,
                        11,
                        6,
                        1,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "thu": [
                        18,
                        23,
                        28,
                        33,
                        38,
                        43,
                        48,
                        53,
                        58,
                        53,
                        48,
                        43,
                        38,
                        33,
                        28,
                        23,
                        18,
                        13,
                        8,
                        3,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "fri": [
                        20,
                        25,
                        30,
                        35,
                        40,
                        45,
                        50,
                        55,
                        60,
                        55,
                        50,
                        45,
                        40,
                        35,
                        30,
                        25,
                        20,
                        15,
                        10,
                        5,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "sat": [
                        22,
                        27,
                        32,
                        37,
                        42,
                        47,
                        52,
                        57,
                        62,
                        57,
                        52,
                        47,
                        42,
                        37,
                        32,
                        27,
                        22,
                        17,
                        12,
                        7,
                        2,
                        0,
                        0,
                        0,
                    ],
                },
            ),
            get_dashboard_summary=AsyncMock(
                spec=AnalyticsManager.get_dashboard_summary,
                return_value={
                    "species_total": 107,
                    "detections_today": 150,
                    "species_week": 85,
                    "storage": 123456789,
                },
            ),
        )
        return mock

    @pytest.fixture
    def presentation_manager(self, mock_analytics_manager):
        """Create presentation manager with mocked dependencies."""
        config = MagicMock(
            spec=BirdNETConfig,
            site_name="Test Site",
            species_confidence_threshold=0.8,
            language="en",
            latitude=40.7128,
            longitude=-74.006,
            timezone="UTC",
        )
        manager = PresentationManager(
            config=config,
            analytics_manager=mock_analytics_manager,
            detection_query_service=MagicMock(spec=DetectionQueryService),
        )
        return manager

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "period,expected_label,expected_new_species_period,extra_checks",
        [
            pytest.param(
                "day",
                "Today",
                "week",
                {
                    "today_species": 5,
                    "today_detections": 603,
                    "peak_activity_time": "08:00-09:00",
                    "peak_detections": 40,
                    "new_species_max_len": 2,
                },
                id="day-view-with-detailed-counts",
            ),
            pytest.param(
                "week",
                "This Week",
                "period",
                {"peak_activity_time_options": ["06:00-07:00", "08:00-09:00"]},
                id="week-view-with-aggregated-peak",
            ),
            pytest.param(
                "season",
                "This Season",
                "period",
                None,
                id="season-view",
            ),
            pytest.param(
                "historical",
                "All Time",
                "period",
                None,
                id="historical-view",
            ),
        ],
    )
    async def test_period_view_statistics(
        self,
        presentation_manager,
        period,
        expected_label,
        expected_new_species_period,
        extra_checks,
    ):
        """Should show correct statistics for different period views."""
        mock_detection_query_service = MagicMock(spec=DetectionQueryService)
        mock_detection_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {
                    "scientific_name": "Turdus migratorius",
                    "common_name": "American Robin",
                    "detection_count": 250,
                },
                {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "detection_count": 200,
                },
                {
                    "scientific_name": "Cyanocitta cristata",
                    "common_name": "Blue Jay",
                    "detection_count": 150,
                },
                {
                    "scientific_name": "Rare species 1",
                    "common_name": None,
                    "detection_count": 2,
                },
                {
                    "scientific_name": "Rare species 2",
                    "common_name": None,
                    "detection_count": 1,
                },
            ],
        )
        result = await presentation_manager.get_detection_display_data(
            period=period, detection_query_service=mock_detection_query_service
        )

        # Common assertions for all periods
        assert result["period_label"] == expected_label
        assert result["new_species_period"] == expected_new_species_period

        # Period-specific assertions
        if extra_checks:
            if "today_species" in extra_checks:
                assert result["today_species"] == extra_checks["today_species"]
            if "today_detections" in extra_checks:
                assert result["today_detections"] == extra_checks["today_detections"]
            if "peak_activity_time" in extra_checks:
                assert result["peak_activity_time"] == extra_checks["peak_activity_time"]
            if "peak_detections" in extra_checks:
                assert result["peak_detections"] == extra_checks["peak_detections"]
            if "new_species_max_len" in extra_checks:
                assert len(result["new_species"]) <= extra_checks["new_species_max_len"]
            if "peak_activity_time_options" in extra_checks:
                assert result["peak_activity_time"] in extra_checks["peak_activity_time_options"]
                assert isinstance(result["peak_detections"], int)

    @pytest.mark.asyncio
    async def test_rare_species_identification(self, presentation_manager):
        """Should correctly identify rare species as 'new'."""
        mock_detection_query_service = MagicMock(spec=DetectionQueryService)
        mock_detection_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {
                    "scientific_name": "Turdus migratorius",
                    "common_name": "American Robin",
                    "detection_count": 250,
                },
                {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "detection_count": 200,
                },
                {
                    "scientific_name": "Cyanocitta cristata",
                    "common_name": "Blue Jay",
                    "detection_count": 150,
                },
                {
                    "scientific_name": "Rare species 1",
                    "common_name": None,
                    "detection_count": 2,
                },
                {
                    "scientific_name": "Rare species 2",
                    "common_name": None,
                    "detection_count": 1,
                },
            ],
        )
        result = await presentation_manager.get_detection_display_data(
            period="week", detection_query_service=mock_detection_query_service
        )
        new_species = result["new_species"]
        assert len(new_species) > 0
        assert len(new_species) <= 2
        for species_name in new_species:
            assert "Rare species" in species_name

    @pytest.mark.asyncio
    async def test_no_data_handling(self, presentation_manager):
        """Should handle no detection data gracefully."""
        empty_service = MagicMock(spec=DetectionQueryService)
        empty_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[],
        )
        presentation_manager.analytics_manager.get_temporal_patterns = AsyncMock(
            spec=AnalyticsManager.get_temporal_patterns,
            return_value={"hourly_distribution": [], "peak_hour": None, "periods": {}},
        )
        result = await presentation_manager.get_detection_display_data(
            period="day", detection_query_service=empty_service
        )
        assert result["today_species"] == 0
        assert result["today_detections"] == 0
        assert result["new_species"] == []
        assert "06:00" in result["peak_activity_time"]

    @pytest.mark.parametrize(
        "period,expected_label",
        [
            ("day", "Today"),
            ("week", "This Week"),
            ("month", "This Month"),
            ("season", "This Season"),
            ("year", "This Year"),
            ("historical", "All Time"),
            ("unknown", "This Period"),
        ],
    )
    def test_period_label_helper(self, presentation_manager, period, expected_label):
        """Should return correct labels from period label helper."""
        assert presentation_manager._get_period_label(period) == expected_label
