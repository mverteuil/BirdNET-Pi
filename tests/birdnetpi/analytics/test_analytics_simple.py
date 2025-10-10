"""Simple tests for AnalyticsManager that actually work."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import Detection, DetectionWithTaxa
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_config():
    """Mock config."""
    config = MagicMock(
        spec=BirdNETConfig, confidence_threshold=0.7, species_confidence_threshold=0.03
    )
    return config


@pytest.fixture
def mock_detection_query_service():
    """Mock detection query service."""
    mock = MagicMock(
        spec=DetectionQueryService,
        get_detection_count=AsyncMock(
            spec=DetectionQueryService.get_detection_count, return_value=100
        ),
        get_unique_species_count=AsyncMock(
            spec=DetectionQueryService.get_unique_species_count, return_value=25
        ),
        get_storage_metrics=AsyncMock(
            spec=DetectionQueryService.get_storage_metrics,
            return_value={"total_bytes": 1073741824, "total_duration": 7200, "total_files": 100},
        ),
        get_species_counts=AsyncMock(
            spec=DetectionQueryService.get_species_counts, return_value=[]
        ),
        get_hourly_counts=AsyncMock(spec=DetectionQueryService.get_hourly_counts, return_value=[]),
        query_detections=AsyncMock(spec=DetectionQueryService.query_detections, return_value=[]),
    )
    return mock


@pytest.fixture
def analytics_manager(mock_detection_query_service, test_config):
    """Create AnalyticsManager."""
    return AnalyticsManager(mock_detection_query_service, test_config)


class TestAnalyticsManagerBasics:
    """Basic AnalyticsManager functionality."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary(self, analytics_manager, mock_detection_query_service):
        """Should dashboard summary generation."""
        mock_detection_query_service.get_detection_count.return_value = 50
        mock_detection_query_service.get_unique_species_count.side_effect = [30, 15]
        summary = await analytics_manager.get_dashboard_summary()
        assert "species_total" in summary
        assert "detections_today" in summary
        assert "species_week" in summary
        assert "storage_gb" in summary
        assert "hours_monitored" in summary
        assert "confidence_threshold" in summary
        assert summary["species_total"] == 30
        assert summary["detections_today"] == 50
        assert summary["species_week"] == 15
        assert summary["storage_gb"] == 1.0
        assert summary["confidence_threshold"] == 0.7

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should analyze species frequency correctly."""
        mock_species = [
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "count": 100,
            },
            {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "count": 50},
        ]
        mock_detection_query_service.get_species_counts.return_value = mock_species
        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)
        assert len(analysis) == 2
        assert all("name" in item for item in analysis)
        assert all("count" in item for item in analysis)
        assert all("percentage" in item for item in analysis)
        assert all("category" in item for item in analysis)
        assert analysis[0]["name"] == "American Robin"
        assert analysis[0]["count"] == 100
        assert analysis[0]["category"] == "common"
        assert analysis[1]["name"] == "Blue Jay"
        assert analysis[1]["count"] == 50
        assert analysis[1]["category"] == "common"

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics_manager, mock_detection_query_service):
        """Should temporal pattern analysis."""
        hourly_counts = [
            {"hour": 0, "count": 5},
            {"hour": 6, "count": 15},
            {"hour": 12, "count": 20},
            {"hour": 18, "count": 10},
        ]
        mock_detection_query_service.get_hourly_counts.return_value = hourly_counts
        patterns = await analytics_manager.get_temporal_patterns(date=date(2024, 1, 15))
        assert "hourly_distribution" in patterns
        assert "peak_hour" in patterns
        assert "periods" in patterns
        assert len(patterns["hourly_distribution"]) == 24
        assert patterns["hourly_distribution"][0] == 5
        assert patterns["hourly_distribution"][6] == 15
        assert patterns["hourly_distribution"][12] == 20

    @pytest.mark.asyncio
    async def test_get_weekly_patterns(self, analytics_manager, mock_detection_query_service):
        """Should weekly pattern generation."""
        patterns = await analytics_manager.get_weekly_patterns()
        assert len(patterns) == 7
        assert "sun" in patterns
        assert "mon" in patterns
        assert "sat" in patterns
        for day_pattern in patterns.values():
            assert len(day_pattern) == 24

    @pytest.mark.asyncio
    async def test_get_weekly_heatmap_data(self, analytics_manager, mock_detection_query_service):
        """Should weekly heatmap data generation."""
        heatmap = await analytics_manager.get_weekly_heatmap_data(days=7)
        assert len(heatmap) == 7
        for row in heatmap:
            assert len(row) == 24

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should generate scatter plot data correctly."""
        detection = Detection(
            id=uuid4(),
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime.now(UTC).replace(hour=8, minute=30),
            audio_file_id=uuid4(),
        )
        mock_detections = [
            DetectionWithTaxa(
                detection=detection, ioc_english_name="American Robin", translated_name=None
            )
        ]
        mock_detection_query_service.query_detections.return_value = mock_detections
        mock_detection_query_service.get_species_counts.return_value = [
            {"common_name": "American Robin", "count": 1}
        ]
        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)
        assert isinstance(scatter_data, list)
        assert len(scatter_data) == 1
        point = scatter_data[0]
        assert "time" in point
        assert "confidence" in point
        assert "common_name" in point
        assert "frequency_category" in point
        assert point["time"] == 8.5
        assert point["confidence"] == 0.95
        assert point["common_name"] == "American Robin"
        assert point["frequency_category"] == "uncommon"
