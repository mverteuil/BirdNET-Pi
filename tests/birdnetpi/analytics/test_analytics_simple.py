"""Simple tests for AnalyticsManager that actually work."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_config():
    """Mock config."""
    config = MagicMock(spec=BirdNETConfig)
    config.confidence_threshold = 0.7
    config.species_confidence_threshold = 0.03
    return config


@pytest.fixture
def mock_detection_query_service():
    """Mock detection query service."""
    mock = MagicMock(spec=DetectionQueryService)
    # Set up default async returns
    mock.get_detection_count = AsyncMock(return_value=100)
    mock.get_unique_species_count = AsyncMock(return_value=25)
    mock.get_storage_metrics = AsyncMock(
        return_value={"total_bytes": 1073741824, "total_duration": 7200, "total_files": 100}
    )
    mock.get_species_counts = AsyncMock(return_value=[])
    mock.get_hourly_counts = AsyncMock(return_value=[])
    mock.query_detections = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def analytics_manager(mock_detection_query_service, mock_config):
    """Create AnalyticsManager."""
    return AnalyticsManager(mock_detection_query_service, mock_config)


class TestAnalyticsManagerBasics:
    """Test basic AnalyticsManager functionality."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary(self, analytics_manager, mock_detection_query_service):
        """Test dashboard summary generation."""
        # Setup specific returns
        mock_detection_query_service.get_detection_count.return_value = 50
        mock_detection_query_service.get_unique_species_count.side_effect = [30, 15]  # total, week

        # Execute
        summary = await analytics_manager.get_dashboard_summary()

        # Verify structure
        assert "species_total" in summary
        assert "detections_today" in summary
        assert "species_week" in summary
        assert "storage_gb" in summary
        assert "hours_monitored" in summary
        assert "confidence_threshold" in summary

        # Verify values
        assert summary["species_total"] == 30
        assert summary["detections_today"] == 50
        assert summary["species_week"] == 15
        assert summary["storage_gb"] == 1.0  # 1073741824 / (1024**3)
        assert summary["confidence_threshold"] == 0.03  # species_confidence_threshold from config

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis(
        self, analytics_manager, mock_detection_query_service
    ):
        """Test species frequency analysis."""
        # Setup mock species data
        mock_species = [
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "count": 100,
            },
            {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "count": 50},
        ]
        mock_detection_query_service.get_species_counts.return_value = mock_species

        # Execute
        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        # Verify
        assert len(analysis) == 2
        assert all("name" in item for item in analysis)
        assert all("count" in item for item in analysis)
        assert all("percentage" in item for item in analysis)
        assert all("category" in item for item in analysis)

        # Verify values
        assert analysis[0]["name"] == "American Robin"  # Uses common_name
        assert analysis[0]["count"] == 100
        assert analysis[0]["category"] == "common"  # >20 detections
        assert analysis[1]["name"] == "Blue Jay"
        assert analysis[1]["count"] == 50
        assert analysis[1]["category"] == "common"  # >20 detections

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics_manager, mock_detection_query_service):
        """Test temporal pattern analysis."""
        # Setup hourly data
        hourly_counts = [
            {"hour": 0, "count": 5},
            {"hour": 6, "count": 15},
            {"hour": 12, "count": 20},
            {"hour": 18, "count": 10},
        ]
        mock_detection_query_service.get_hourly_counts.return_value = hourly_counts

        # Execute
        patterns = await analytics_manager.get_temporal_patterns(date=date(2024, 1, 15))

        # Verify structure
        assert "hourly_distribution" in patterns
        assert "peak_hour" in patterns
        assert "periods" in patterns

        # Verify hourly distribution has 24 hours
        assert len(patterns["hourly_distribution"]) == 24
        assert patterns["hourly_distribution"][0] == 5
        assert patterns["hourly_distribution"][6] == 15
        assert patterns["hourly_distribution"][12] == 20

    @pytest.mark.asyncio
    async def test_get_weekly_patterns(self, analytics_manager, mock_detection_query_service):
        """Test weekly pattern generation."""
        # Mock will return empty list, should handle gracefully
        patterns = await analytics_manager.get_weekly_patterns()

        # Should return dict with 7 days
        assert len(patterns) == 7
        assert "sun" in patterns
        assert "mon" in patterns
        assert "sat" in patterns

        # Each day should have 24 hours
        for day_pattern in patterns.values():
            assert len(day_pattern) == 24

    @pytest.mark.asyncio
    async def test_get_weekly_heatmap_data(self, analytics_manager, mock_detection_query_service):
        """Test weekly heatmap data generation."""
        # Execute
        heatmap = await analytics_manager.get_weekly_heatmap_data(days=7)

        # Verify structure - 7 days x 24 hours
        assert len(heatmap) == 7
        for row in heatmap:
            assert len(row) == 24

    def test_calculate_correlation(self, analytics_manager):
        """Test correlation calculation."""
        # Test perfect positive correlation
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        corr = analytics_manager.calculate_correlation(x, y)
        assert 0.99 <= corr <= 1.0

        # Test perfect negative correlation
        y_neg = [10, 8, 6, 4, 2]
        corr_neg = analytics_manager.calculate_correlation(x, y_neg)
        assert -1.0 <= corr_neg <= -0.99

        # Test empty lists
        assert analytics_manager.calculate_correlation([], []) == 0

        # Test single value
        assert analytics_manager.calculate_correlation([1], [1]) == 0

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data(
        self, analytics_manager, mock_detection_query_service
    ):
        """Test scatter plot data generation."""
        # Setup mock detections
        from datetime import UTC
        from uuid import uuid4

        from birdnetpi.detections.models import Detection, DetectionWithTaxa

        detection = Detection(
            id=uuid4(),
            species_tensor="Turdus migratorius_American Robin",  # Required field
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime.now(UTC).replace(hour=8, minute=30),
            audio_file_id=uuid4(),
        )

        # Wrap in DetectionWithTaxa to add localization fields
        mock_detections = [
            DetectionWithTaxa(
                detection=detection,
                ioc_english_name="American Robin",
                translated_name=None,  # No translation available
            )
        ]
        mock_detection_query_service.query_detections.return_value = mock_detections

        # Execute
        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        # Verify
        assert isinstance(scatter_data, list)
        assert len(scatter_data) == 1

        point = scatter_data[0]
        assert "time" in point
        assert "confidence" in point
        assert "species" in point
        assert "frequency_category" in point

        # Verify values
        assert point["time"] == 8.5  # 8:30 = 8 + 30/60
        assert point["confidence"] == 0.95
        assert point["species"] == "American Robin"  # Uses ioc_english_name
        assert point["frequency_category"] == "uncommon"  # 1 detection is <= 5
