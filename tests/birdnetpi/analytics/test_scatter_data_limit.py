"""Test that scatter data handles more than 100 detections correctly."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_detection_query_service():
    """Create a mock DetectionQueryService."""
    return MagicMock(spec=DetectionQueryService)


@pytest.fixture
def analytics_manager(mock_detection_query_service, test_config):
    """Create an AnalyticsManager with mocked dependencies."""
    return AnalyticsManager(mock_detection_query_service, test_config)


class TestScatterDataLimit:
    """Scatter data properly handles high detection volumes."""

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_uses_higher_limit(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should use limit=1000 to avoid truncation at 100 detections."""
        # Create 150 real detections to simulate a busy day
        detections = []
        base_time = datetime.now()

        for i in range(150):
            # Spread detections across 24 hours
            hour_offset = i % 24
            detection = model_factory.create_detection_with_taxa(
                timestamp=base_time.replace(hour=hour_offset, minute=i % 60, second=0),
                confidence=0.5 + (i % 50) / 100,  # Vary confidence
                scientific_name=f"Species_{i % 10}",
                common_name=f"Bird_{i % 10}",
                ioc_english_name=f"IOC_Bird_{i % 10}",
            )
            detections.append(detection)

        mock_detection_query_service.query_detections = AsyncMock(
            spec=callable, return_value=detections
        )

        # Mock species counts for frequency categorization
        species_counts = []
        for i in range(10):
            species_counts.append({"common_name": f"Bird_{i}", "count": 15})  # 15 each = 150 total
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=callable, return_value=species_counts
        )

        # Call the method
        result = await analytics_manager.get_detection_scatter_data(hours=24)

        # Verify the query was made with the correct limit
        mock_detection_query_service.query_detections.assert_called_once()
        call_args = mock_detection_query_service.query_detections.call_args

        # Check that limit=1000 was passed
        assert call_args.kwargs.get("limit") == 1000

        # Verify all 150 detections are included in the result
        assert len(result) == 150

        # Verify data structure is correct
        for item in result:
            assert "time" in item
            assert "confidence" in item
            assert "common_name" in item
            assert "frequency_category" in item

            # Time should be between 0 and 24
            assert 0 <= item["time"] < 24

            # Confidence should be between 0 and 1
            assert 0 <= item["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_handles_empty_response(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should handle case with no detections gracefully."""
        mock_detection_query_service.query_detections = AsyncMock(spec=callable, return_value=[])
        mock_detection_query_service.get_species_counts = AsyncMock(spec=callable, return_value=[])

        result = await analytics_manager.get_detection_scatter_data(hours=24)

        # Should return empty list
        assert result == []

        # Should still have requested with limit=1000
        call_args = mock_detection_query_service.query_detections.call_args
        assert call_args.kwargs.get("limit") == 1000

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_frequency_categorization(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should correctly categorize species by frequency."""
        detections = []
        base_time = datetime.now()

        # Create detections with different frequencies
        # Species_1: 25 detections (common - needs >20)
        for i in range(25):
            detection = model_factory.create_detection_with_taxa(
                timestamp=base_time.replace(hour=i % 24, minute=0, second=0),
                confidence=0.8,
                scientific_name="Species_1",
                common_name="Common Bird",
                ioc_english_name="Common Bird",
            )
            detections.append(detection)

        # Species_2: 10 detections (regular - needs >5 and <=20)
        for i in range(10):
            detection = model_factory.create_detection_with_taxa(
                timestamp=base_time.replace(hour=i % 24, minute=30, second=0),
                confidence=0.7,
                scientific_name="Species_2",
                common_name="Regular Bird",
                ioc_english_name="Regular Bird",
            )
            detections.append(detection)

        # Species_3: 1 detection (uncommon)
        detection = model_factory.create_detection_with_taxa(
            timestamp=base_time.replace(hour=12, minute=45, second=0),
            confidence=0.6,
            scientific_name="Species_3",
            common_name="Rare Bird",
            ioc_english_name="Rare Bird",
        )
        detections.append(detection)

        mock_detection_query_service.query_detections = AsyncMock(
            spec=callable, return_value=detections
        )

        # Mock species counts for frequency categorization
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=callable,
            return_value=[
                {"common_name": "Common Bird", "count": 25},
                {"common_name": "Regular Bird", "count": 10},
                {"common_name": "Rare Bird", "count": 1},
            ],
        )

        result = await analytics_manager.get_detection_scatter_data(hours=24)

        # Group results by species
        species_categories = {}
        for item in result:
            species_categories[item["common_name"]] = item["frequency_category"]

        # Check frequency categorization
        # Common Bird should be 'common' (25 detections, >20)
        assert species_categories.get("Common Bird") == "common"

        # Regular Bird should be 'regular' (10 detections, >5 and <=20)
        assert species_categories.get("Regular Bird") == "regular"

        # Rare Bird should be 'uncommon' (1 detection)
        assert species_categories.get("Rare Bird") == "uncommon"
