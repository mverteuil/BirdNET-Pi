"""Unit tests for AnalyticsManager."""

from datetime import date, datetime
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


class TestDashboardAnalytics:
    """Test dashboard analytics methods."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary(
        self, analytics_manager, mock_detection_query_service, test_config
    ):
        """Should calculate dashboard summary with correct metrics."""
        # Mock DetectionQueryService methods
        # Use the class methods for spec, not the mock instance methods
        mock_detection_query_service.get_detection_count = AsyncMock(
            spec=DetectionQueryService.get_detection_count, return_value=150
        )
        mock_detection_query_service.get_unique_species_count = AsyncMock(
            spec=DetectionQueryService.get_unique_species_count, side_effect=[50, 25]
        )  # total, week
        mock_detection_query_service.get_storage_metrics = AsyncMock(
            spec=DetectionQueryService.get_storage_metrics,
            return_value={
                "total_bytes": 1024 * 1024 * 1024 * 5,  # 5GB
                "total_duration": 3600 * 24,  # 24 hours
            },
        )

        summary = await analytics_manager.get_dashboard_summary()

        assert summary["detections_today"] == 150
        assert summary["species_total"] == 50
        assert summary["species_week"] == 25
        assert summary["storage_gb"] == 5.0
        assert summary["hours_monitored"] == 24.0
        assert summary["confidence_threshold"] == test_config.species_confidence_threshold

        # Verify correct time ranges were used
        assert mock_detection_query_service.get_detection_count.call_count == 1
        assert mock_detection_query_service.get_unique_species_count.call_count == 2

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should analyze species frequency and categorize by count."""
        # Mock species counts from DataManager
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=DetectionQueryService.get_species_counts,
            return_value=[
                {
                    "scientific_name": "Turdus migratorius",
                    "common_name": "American Robin",
                    "count": 25,
                },
                {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "count": 10,
                },
                {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "count": 3},
            ],
        )

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert len(analysis) == 3

        # Check first species
        assert analysis[0]["name"] == "American Robin"
        assert analysis[0]["count"] == 25
        assert analysis[0]["percentage"] == pytest.approx(25 / 38 * 100)
        assert analysis[0]["category"] == "common"

        # Check second species
        assert analysis[1]["name"] == "Northern Cardinal"
        assert analysis[1]["count"] == 10
        assert analysis[1]["percentage"] == pytest.approx(10 / 38 * 100)
        assert analysis[1]["category"] == "regular"

        # Check third species
        assert analysis[2]["name"] == "Blue Jay"
        assert analysis[2]["count"] == 3
        assert analysis[2]["percentage"] == pytest.approx(3 / 38 * 100)
        assert analysis[2]["category"] == "uncommon"

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_empty(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should return empty list when no species data exists."""
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=DetectionQueryService.get_species_counts, return_value=[]
        )

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert analysis == []

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_no_common_name(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should use scientific name when common name is missing."""
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=DetectionQueryService.get_species_counts,
            return_value=[
                {"scientific_name": "Rare species", "common_name": None, "count": 5},
            ],
        )

        analysis = await analytics_manager.get_species_frequency_analysis(hours=24)

        assert len(analysis) == 1
        assert analysis[0]["name"] == "Rare species"  # Falls back to scientific name


class TestTemporalPatterns:
    """Test temporal pattern analysis methods."""

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics_manager, mock_detection_query_service):
        """Should analyze temporal patterns with hourly detection data."""
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            return_value=[
                {"hour": 6, "count": 15},
                {"hour": 7, "count": 25},
                {"hour": 8, "count": 30},
                {"hour": 12, "count": 10},
                {"hour": 18, "count": 20},
            ],
        )

        patterns = await analytics_manager.get_temporal_patterns(date.today())

        assert "hourly_distribution" in patterns
        assert "peak_hour" in patterns
        assert "periods" in patterns
        assert patterns["hourly_distribution"][6] == 15
        assert patterns["hourly_distribution"][7] == 25
        assert patterns["hourly_distribution"][8] == 30
        assert patterns["peak_hour"] == 8  # Hour with max count (30)
        assert patterns["periods"]["dawn"] == 40  # sum(4-8am) = 0+0+15+25
        assert patterns["periods"]["morning"] == 30  # sum(8-12pm) = 30+0+0+0
        assert patterns["periods"]["afternoon"] == 10  # sum(12-4pm) = 10+0+0+0
        assert patterns["periods"]["evening"] == 20  # sum(4-8pm) = 0+0+20+0

    @pytest.mark.asyncio
    async def test_get_aggregate_hourly_pattern(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate aggregate hourly patterns across multiple days."""
        # Mock hourly counts for each day queried
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            return_value=[
                {"hour": 6, "count": 50},
                {"hour": 7, "count": 75},
                {"hour": 8, "count": 60},
                {"hour": 12, "count": 30},
                {"hour": 18, "count": 45},
            ],
        )

        pattern = await analytics_manager.get_aggregate_hourly_pattern(days=30)

        # Returns 7x24 array (7 days of week, 24 hours each)
        assert len(pattern) == 7  # 7 days of week
        assert len(pattern[0]) == 24  # 24 hours per day
        # Since we're aggregating over 30 days, each day should have accumulated counts
        # Check that some hours have counts > 0
        total_counts = sum(sum(day) for day in pattern)
        assert total_counts > 0  # Should have some accumulated data

    @pytest.mark.asyncio
    async def test_get_weekly_heatmap_data(self, analytics_manager, mock_detection_query_service):
        """Should generate weekly heatmap data for visualization."""
        # Mock different hourly counts for different days
        day_patterns = [
            [{"hour": 6, "count": 10}, {"hour": 7, "count": 15}],  # Day 1
            [{"hour": 6, "count": 12}, {"hour": 8, "count": 20}],  # Day 2
            [{"hour": 18, "count": 25}],  # Day 3
        ]
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            side_effect=day_patterns + [[] for _ in range(4)],  # Fill rest with empty
        )

        heatmap = await analytics_manager.get_weekly_heatmap_data(days=7)

        assert len(heatmap) == 7  # 7 days
        assert len(heatmap[0]) == 24  # 24 hours per day

        # Check specific patterns (note: days are in reverse chronological order)
        assert heatmap[-1][6] == 10  # Oldest day (day 1), hour 6
        assert heatmap[-1][7] == 15  # Oldest day (day 1), hour 7
        assert heatmap[-2][6] == 12  # Day 2, hour 6
        assert heatmap[-2][8] == 20  # Day 2, hour 8

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should generate scatter plot data for detection visualization."""
        test_time = datetime(2024, 1, 1, 6, 30)

        # Use model_factory to create real DetectionWithTaxa instances
        detection1 = model_factory.create_detection_with_taxa(
            timestamp=test_time,
            confidence=0.85,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            ioc_english_name="American Robin",
        )

        detection2 = model_factory.create_detection_with_taxa(
            timestamp=datetime(2024, 1, 1, 7, 15),
            confidence=0.92,
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            ioc_english_name="Northern Cardinal",
        )

        mock_detection_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections,
            return_value=[detection1, detection2],
        )

        # Mock species counts for frequency categorization
        mock_detection_query_service.get_species_counts = AsyncMock(
            spec=DetectionQueryService.get_species_counts,
            return_value=[
                {"common_name": "American Robin", "count": 8},
                {"common_name": "Northern Cardinal", "count": 3},
            ],
        )

        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        assert len(scatter_data) == 2
        assert scatter_data[0]["time"] == 6.5  # 6:30 AM
        assert scatter_data[0]["confidence"] == 0.85
        assert scatter_data[0]["common_name"] == "American Robin"
        assert scatter_data[0]["frequency_category"] == "regular"  # 8 detections = regular
        assert scatter_data[1]["time"] == 7.25  # 7:15 AM
        assert scatter_data[1]["confidence"] == 0.92
        assert scatter_data[1]["frequency_category"] == "uncommon"  # 3 detections = uncommon


class TestDiversityMetrics:
    """Test biodiversity calculation methods."""

    @pytest.mark.asyncio
    async def test_calculate_diversity_timeline(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate diversity metrics over time periods."""
        # Mock the method that calculate_diversity_timeline actually calls
        mock_detection_query_service.get_species_counts_by_period = AsyncMock(
            spec=DetectionQueryService.get_species_counts_by_period,
            return_value=[
                {
                    "period": datetime(2024, 1, 1, 6, 0),
                    "species_counts": {
                        "Species A": 2,
                        "Species B": 1,
                    },
                },
                {
                    "period": datetime(2024, 1, 1, 7, 0),
                    "species_counts": {
                        "Species B": 1,
                        "Species C": 1,
                    },
                },
                {
                    "period": datetime(2024, 1, 1, 8, 0),
                    "species_counts": {
                        "Species C": 1,
                    },
                },
            ],
        )

        timeline = await analytics_manager.calculate_diversity_timeline(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            temporal_resolution="hourly",
        )

        assert len(timeline) > 0
        assert "period" in timeline[0]
        assert "shannon" in timeline[0]
        assert "simpson" in timeline[0]
        assert "richness" in timeline[0]
        assert "evenness" in timeline[0]
        # Shannon index should be > 0 when multiple species present
        assert any(point["shannon"] > 0 for point in timeline)

    @pytest.mark.asyncio
    async def test_calculate_species_accumulation(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate species accumulation curve."""
        # Mock the actual method called by calculate_species_accumulation
        # Returns list of tuples (timestamp, species_name)
        mock_detection_query_service.get_detections_for_accumulation = AsyncMock(
            spec=DetectionQueryService.get_detections_for_accumulation,
            return_value=[
                (datetime(2024, 1, 1, 6, 0), "Species A"),
                (datetime(2024, 1, 1, 7, 0), "Species B"),
                (datetime(2024, 1, 1, 8, 0), "Species A"),  # Repeat
                (datetime(2024, 1, 1, 9, 0), "Species C"),
                (datetime(2024, 1, 1, 10, 0), "Species D"),
            ],
        )

        accumulation = await analytics_manager.calculate_species_accumulation(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            method="collector",  # Use collector method for actual observation order
        )

        assert len(accumulation["samples"]) > 0
        assert len(accumulation["species_counts"]) > 0
        assert accumulation["species_counts"][0] == 1  # First species
        assert accumulation["species_counts"][-1] == 4  # Total unique species (4 distinct)
        assert accumulation["method"] == "collector"

    @pytest.mark.asyncio
    async def test_calculate_community_similarity(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate community similarity between time periods."""
        # Mock the method that calculate_community_similarity actually calls
        # Returns species counts for each period
        mock_detection_query_service.get_species_counts_for_periods = AsyncMock(
            spec=DetectionQueryService.get_species_counts_for_periods,
            return_value=[
                {"Species A": 2, "Species B": 1, "Species C": 1},  # Period 1
                {"Species A": 1, "Species B": 1, "Species D": 1},  # Period 2
            ],
        )

        similarity = await analytics_manager.calculate_community_similarity(
            periods=[
                (datetime(2024, 1, 1), datetime(2024, 1, 2)),
                (datetime(2024, 1, 3), datetime(2024, 1, 4)),
            ],
            index_type="jaccard",
        )

        assert "labels" in similarity
        assert "matrix" in similarity
        assert "index_type" in similarity
        assert similarity["index_type"] == "jaccard"
        # Matrix should be 2x2 (2 periods)
        assert len(similarity["matrix"]) == 2
        assert len(similarity["matrix"][0]) == 2
        # Diagonal should be 1.0 (perfect similarity with self)
        assert similarity["matrix"][0][0] == 1.0
        assert similarity["matrix"][1][1] == 1.0
        # Off-diagonal should be the Jaccard similarity
        # 2 shared species (A, B) out of 4 total unique species = 0.5
        assert similarity["matrix"][0][1] == pytest.approx(0.5, rel=0.01)

    @pytest.mark.parametrize(
        "count,expected_category",
        [
            # Uncommon (<=5)
            pytest.param(0, "uncommon", id="zero_count"),
            pytest.param(1, "uncommon", id="single_detection"),
            pytest.param(3, "uncommon", id="few_detections"),
            pytest.param(5, "uncommon", id="threshold_uncommon"),
            # Regular (6-20)
            pytest.param(6, "regular", id="threshold_regular_min"),
            pytest.param(8, "regular", id="mid_regular"),
            pytest.param(20, "regular", id="threshold_regular_max"),
            # Common (>20)
            pytest.param(21, "common", id="threshold_common"),
            pytest.param(25, "common", id="many_detections"),
            pytest.param(100, "common", id="very_many_detections"),
        ],
    )
    def test_categorize_frequency(self, analytics_manager, count, expected_category):
        """Should categorize species counts into frequency categories correctly."""
        assert analytics_manager._categorize_frequency(count) == expected_category


class TestTemporalAnalytics:
    """Test temporal pattern analytics."""

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics_manager, mock_detection_query_service):
        """Should analyze temporal patterns and identify peak hours."""
        # Mock hourly counts from DataManager
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            return_value=[
                {"hour": 6, "count": 15},
                {"hour": 7, "count": 25},
                {"hour": 8, "count": 20},
                {"hour": 12, "count": 10},
                {"hour": 17, "count": 8},
                {"hour": 18, "count": 12},
                {"hour": 20, "count": 5},
            ],
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
    async def test_get_temporal_patterns_no_date(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should use today's date when no date is provided."""
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts, return_value=[]
        )

        await analytics_manager.get_temporal_patterns()

        # Should call with today's date
        called_date = mock_detection_query_service.get_hourly_counts.call_args[0][0]
        assert called_date == datetime.now().date()

    @pytest.mark.asyncio
    async def test_get_temporal_patterns_empty(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should return zero counts and default peak hour when no data exists."""
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts, return_value=[]
        )

        patterns = await analytics_manager.get_temporal_patterns(date(2024, 1, 1))

        # Should have zeros for all hours
        assert all(count == 0 for count in patterns["hourly_distribution"])
        # Peak hour defaults to 6 AM (typical bird activity time) when no data
        assert patterns["peak_hour"] == 6
        # Check all 6 periods are present and zero
        expected_periods = ["night_early", "dawn", "morning", "afternoon", "evening", "night_late"]
        assert set(patterns["periods"].keys()) == set(expected_periods)
        assert all(patterns["periods"][period] == 0 for period in patterns["periods"])


class TestScatterVisualization:
    """Test detection scatter data preparation."""

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should prepare scatter plot data with time and confidence values."""
        # Create mock detections with taxa
        detections = [
            model_factory.create_detection_with_taxa(
                detection=model_factory.create_detection(
                    species_tensor="Turdus migratorius_American Robin",
                    scientific_name="Turdus migratorius",
                    common_name="American Robin",
                    confidence=0.95,
                    timestamp=datetime(2024, 1, 1, 6, 15, 0),
                ),
                ioc_english_name="American Robin",
                translated_name="American Robin",
                family="Turdidae",
                genus="Turdus",
                order_name="Passeriformes",
            ),
            model_factory.create_detection_with_taxa(
                detection=model_factory.create_detection(
                    species_tensor="Cardinalis cardinalis_Northern Cardinal",
                    scientific_name="Cardinalis cardinalis",
                    common_name="Northern Cardinal",
                    confidence=0.88,
                    timestamp=datetime(2024, 1, 1, 7, 30, 0),
                ),
                ioc_english_name="Northern Cardinal",
                translated_name="Northern Cardinal",
                family="Cardinalidae",
                genus="Cardinalis",
                order_name="Passeriformes",
            ),
            model_factory.create_detection_with_taxa(
                detection=model_factory.create_detection(
                    species_tensor="Cyanocitta cristata_Blue Jay",
                    scientific_name="Cyanocitta cristata",
                    common_name="Blue Jay",
                    confidence=0.75,
                    timestamp=datetime(2024, 1, 1, 8, 45, 0),
                ),
                ioc_english_name="Blue Jay",
                translated_name="Blue Jay",
                family="Corvidae",
                genus="Cyanocitta",
                order_name="Passeriformes",
            ),
        ]

        mock_detection_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=detections
        )

        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        assert len(scatter_data) == 3

        # Check first detection
        assert scatter_data[0]["time"] == 6.25  # 6:15 = 6 + 15/60
        assert scatter_data[0]["confidence"] == 0.95
        assert scatter_data[0]["common_name"] == "American Robin"
        assert scatter_data[0]["frequency_category"] == "uncommon"  # Count is 1

        # Check second detection
        assert scatter_data[1]["time"] == 7.5  # 7:30 = 7 + 30/60
        assert scatter_data[1]["confidence"] == 0.88
        assert scatter_data[1]["common_name"] == "Northern Cardinal"

        # Check third detection
        assert scatter_data[2]["time"] == 8.75  # 8:45 = 8 + 45/60
        assert scatter_data[2]["confidence"] == 0.75
        assert scatter_data[2]["common_name"] == "Blue Jay"

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_empty(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should return empty list when no detections exist."""
        mock_detection_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=[]
        )

        scatter_data = await analytics_manager.get_detection_scatter_data(hours=24)

        assert scatter_data == []
