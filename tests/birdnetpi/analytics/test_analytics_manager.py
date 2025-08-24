"""Unit tests for AnalyticsManager."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.data_manager import DataManager


@pytest.fixture
def mock_data_manager():
    """Create a mock DataManager."""
    return MagicMock(spec=DataManager)


@pytest.fixture
def mock_config():
    """Create a mock BirdNETConfig."""
    config = MagicMock(spec=BirdNETConfig)
    config.species_confidence_threshold = 0.5
    return config


@pytest.fixture
def analytics_manager(mock_data_manager, mock_config):
    """Create an AnalyticsManager with mocked dependencies."""
    return AnalyticsManager(mock_data_manager, mock_config)


class TestDashboardAnalytics:
    """Test dashboard analytics methods."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary(self, analytics_manager, mock_data_manager, mock_config):
        """Test dashboard summary calculation."""
        # Mock DataManager methods
        mock_data_manager.get_detection_count = AsyncMock(return_value=150)
        mock_data_manager.get_unique_species_count = AsyncMock(side_effect=[50, 25])  # total, week
        mock_data_manager.get_storage_metrics = AsyncMock(
            return_value={
                "total_bytes": 1024 * 1024 * 1024 * 5,  # 5GB
                "total_duration": 3600 * 24,  # 24 hours
            }
        )

        summary = await analytics_manager.get_dashboard_summary()

        assert summary["detections_today"] == 150
        assert summary["species_total"] == 50
        assert summary["species_week"] == 25
        assert summary["storage_gb"] == 5.0
        assert summary["hours_monitored"] == 24.0
        assert summary["confidence_threshold"] == 0.5

        # Verify correct time ranges were used
        assert mock_data_manager.get_detection_count.call_count == 1
        assert mock_data_manager.get_unique_species_count.call_count == 2

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis(self, analytics_manager, mock_data_manager):
        """Test species frequency analysis."""
        # Mock species counts from DataManager
        mock_data_manager.get_species_counts = AsyncMock(
            return_value=[
                {
                    "scientific_name": "Turdus migratorius",
                    "common_name": "American Robin",
                    "count": 250,
                },
                {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "count": 100,
                },
                {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "count": 30},
            ]
        )

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert len(analysis) == 3

        # Check first species
        assert analysis[0]["name"] == "American Robin"
        assert analysis[0]["count"] == 250
        assert analysis[0]["percentage"] == pytest.approx(250 / 380 * 100)
        assert analysis[0]["category"] == "common"

        # Check second species
        assert analysis[1]["name"] == "Northern Cardinal"
        assert analysis[1]["count"] == 100
        assert analysis[1]["percentage"] == pytest.approx(100 / 380 * 100)
        assert analysis[1]["category"] == "regular"

        # Check third species
        assert analysis[2]["name"] == "Blue Jay"
        assert analysis[2]["count"] == 30
        assert analysis[2]["percentage"] == pytest.approx(30 / 380 * 100)
        assert analysis[2]["category"] == "uncommon"

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_empty(self, analytics_manager, mock_data_manager):
        """Test species frequency analysis with no data."""
        mock_data_manager.get_species_counts = AsyncMock(return_value=[])

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert analysis == []

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_no_common_name(
        self, analytics_manager, mock_data_manager
    ):
        """Test species frequency analysis when common name is missing."""
        mock_data_manager.get_species_counts = AsyncMock(
            return_value=[
                {"scientific_name": "Rare species", "common_name": None, "count": 5},
            ]
        )

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert len(analysis) == 1
        assert analysis[0]["name"] == "Rare species"  # Falls back to scientific name


class TestTemporalAnalytics:
    """Test temporal pattern analytics."""

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics_manager, mock_data_manager):
        """Test temporal pattern analysis."""
        # Mock hourly counts from DataManager
        mock_data_manager.get_hourly_counts = AsyncMock(
            return_value=[
                {"hour": 6, "count": 15},
                {"hour": 7, "count": 25},
                {"hour": 8, "count": 20},
                {"hour": 12, "count": 10},
                {"hour": 17, "count": 8},
                {"hour": 18, "count": 12},
                {"hour": 20, "count": 5},
            ]
        )

        patterns = await analytics_manager.get_temporal_patterns(date(2024, 1, 1))

        # Check hourly distribution
        assert patterns["hourly_distribution"][6] == 15
        assert patterns["hourly_distribution"][7] == 25
        assert patterns["hourly_distribution"][8] == 20
        assert patterns["hourly_distribution"][12] == 10
        assert patterns["hourly_distribution"][17] == 8
        assert patterns["hourly_distribution"][18] == 12
        assert patterns["hourly_distribution"][20] == 5

        # Check peak hour
        assert patterns["peak_hour"] == 7  # Hour with max count (25)

        # Check period aggregations (6 equal 4-hour periods)
        assert patterns["periods"]["night_early"] == 0  # 12am-4am: all zeros (hours 0,1,2,3)
        assert patterns["periods"]["dawn"] == 40  # 4am-8am: 0+0+15+25 = 40 (hours 4,5,6,7)
        assert patterns["periods"]["morning"] == 20  # 8am-12pm: 20+0+0+0 = 20 (hours 8,9,10,11)
        assert patterns["periods"]["afternoon"] == 10  # 12pm-4pm: 10+0+0+0 = 10 (hours 12,13,14,15)
        assert patterns["periods"]["evening"] == 20  # 4pm-8pm: 0+8+12+0 = 20 (hours 16,17,18,19)
        assert patterns["periods"]["night_late"] == 5  # 8pm-12am: 5+0+0+0 = 5 (hours 20,21,22,23)

    @pytest.mark.asyncio
    async def test_get_temporal_patterns_no_date(self, analytics_manager, mock_data_manager):
        """Test temporal patterns uses today when no date provided."""
        mock_data_manager.get_hourly_counts = AsyncMock(return_value=[])

        await analytics_manager.get_temporal_patterns()

        # Should call with today's date
        called_date = mock_data_manager.get_hourly_counts.call_args[0][0]
        assert called_date == datetime.now().date()

    @pytest.mark.asyncio
    async def test_get_temporal_patterns_empty(self, analytics_manager, mock_data_manager):
        """Test temporal patterns with no data."""
        mock_data_manager.get_hourly_counts = AsyncMock(return_value=[])

        patterns = await analytics_manager.get_temporal_patterns(date(2024, 1, 1))

        # Should have zeros for all hours
        assert all(count == 0 for count in patterns["hourly_distribution"])
        assert patterns["peak_hour"] is None
        # Check all 6 periods are present and zero
        expected_periods = ["night_early", "dawn", "morning", "afternoon", "evening", "night_late"]
        assert set(patterns["periods"].keys()) == set(expected_periods)
        assert all(patterns["periods"][period] == 0 for period in patterns["periods"])


class TestScatterVisualization:
    """Test detection scatter data preparation."""

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data(self, analytics_manager, mock_data_manager):
        """Test scatter plot data preparation."""
        from birdnetpi.detections.models import Detection

        # Create mock detections
        detections = [
            Detection(
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.95,
                timestamp=datetime(2024, 1, 1, 6, 15, 0),
            ),
            Detection(
                species_tensor="Cardinalis cardinalis_Northern Cardinal",
                scientific_name="Cardinalis cardinalis",
                common_name="Northern Cardinal",
                confidence=0.88,
                timestamp=datetime(2024, 1, 1, 7, 30, 0),
            ),
            Detection(
                species_tensor="Cyanocitta cristata_Blue Jay",
                scientific_name="Cyanocitta cristata",
                common_name="Blue Jay",
                confidence=0.75,
                timestamp=datetime(2024, 1, 1, 8, 45, 0),
            ),
        ]

        mock_data_manager.get_detections_in_range = AsyncMock(return_value=detections)

        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        assert len(scatter_data) == 3

        # Check first detection
        assert scatter_data[0]["time"] == 6.25  # 6:15 = 6 + 15/60
        assert scatter_data[0]["confidence"] == 0.95
        assert scatter_data[0]["species"] == "American Robin"
        assert scatter_data[0]["frequency_category"] == "uncommon"  # Count is 1

        # Check second detection
        assert scatter_data[1]["time"] == 7.5  # 7:30 = 7 + 30/60
        assert scatter_data[1]["confidence"] == 0.88
        assert scatter_data[1]["species"] == "Northern Cardinal"

        # Check third detection
        assert scatter_data[2]["time"] == 8.75  # 8:45 = 8 + 45/60
        assert scatter_data[2]["confidence"] == 0.75
        assert scatter_data[2]["species"] == "Blue Jay"

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_empty(self, analytics_manager, mock_data_manager):
        """Test scatter data with no detections."""
        mock_data_manager.get_detections_in_range = AsyncMock(return_value=[])

        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        assert scatter_data == []


class TestFrequencyCategorization:
    """Test frequency categorization logic."""

    def test_categorize_frequency(self, analytics_manager):
        """Test species frequency categorization."""
        # Test common (>200)
        assert analytics_manager._categorize_frequency(201) == "common"
        assert analytics_manager._categorize_frequency(500) == "common"

        # Test regular (51-200)
        assert analytics_manager._categorize_frequency(51) == "regular"
        assert analytics_manager._categorize_frequency(100) == "regular"
        assert analytics_manager._categorize_frequency(200) == "regular"

        # Test uncommon (<=50)
        assert analytics_manager._categorize_frequency(0) == "uncommon"
        assert analytics_manager._categorize_frequency(1) == "uncommon"
        assert analytics_manager._categorize_frequency(50) == "uncommon"
