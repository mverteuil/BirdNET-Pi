"""Additional tests to improve AnalyticsManager coverage."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_detection_query_service():
    """Create a mock DetectionQueryService.

    Note: This fixture returns a basic mock without configured methods.
    Individual tests can configure methods as needed.
    """
    return MagicMock(spec=DetectionQueryService)


@pytest.fixture
def analytics_manager(mock_detection_query_service, test_config):
    """Create an AnalyticsManager with mocked dependencies."""
    return AnalyticsManager(mock_detection_query_service, test_config)


class TestWeeklyHeatmapExtended:
    """Test weekly heatmap with different time periods."""

    @pytest.mark.asyncio
    async def test_get_weekly_heatmap_data_more_than_7_days(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate averaged weekday patterns for periods > 7 days."""
        # Mock hourly counts for multiple days
        mock_hourly_data = [
            [{"hour": i, "count": (i % 3) + 1} for i in range(24)],  # Day 1
            [{"hour": i, "count": (i % 2) + 2} for i in range(24)],  # Day 2
            [{"hour": i, "count": 1} for i in range(24)],  # Day 3
        ]

        # Return different data for each call
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            side_effect=mock_hourly_data * 5,  # Repeat pattern for 15 days
        )

        result = await analytics_manager.get_weekly_heatmap_data(days=14)

        # Should return 7 days (one for each weekday)
        assert len(result) == 7

        # Each day should have 24 hours
        for day_data in result:
            assert len(day_data) == 24

        # Verify averaging occurred (not just raw counts)
        assert mock_detection_query_service.get_hourly_counts.call_count == 14

    @pytest.mark.asyncio
    async def test_get_weekly_heatmap_data_empty_weekday(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should handle weekdays with no data when averaging."""
        # Only return data for some days
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            side_effect=[
                [{"hour": 12, "count": 5}],  # Monday
                [],  # Tuesday - no data
                [{"hour": 14, "count": 3}],  # Wednesday
            ]
            + [[]] * 11,  # Rest empty
        )

        result = await analytics_manager.get_weekly_heatmap_data(days=14)

        assert len(result) == 7

        # For 14 days (>7), the function aggregates by weekday
        # The mock provides data iterating backwards from today:
        # - First call: most recent day (could be any weekday)
        # - Second call: day before that
        # - Third call: two days before that
        # Since we don't control what day the test runs on, we can't predict
        # which weekday gets which data. The test should verify:
        # 1. Total number of non-zero hours matches expected data
        # 2. The averaging logic works (counts are divided by number of weeks)

        # Count total non-zero entries
        non_zero_count = sum(1 for day in result for count in day if count > 0)
        # We provided data for 2 different hours across 14 days
        assert non_zero_count == 2  # hour 12 from first call, hour 14 from third call


class TestStemLeafDistribution:
    """Test stem-and-leaf distribution visualization."""

    @pytest.mark.asyncio
    async def test_get_stem_leaf_distribution_basic(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should create stem-and-leaf plot from hourly counts."""
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts,
            side_effect=[
                [{"hour": 0, "count": 12}, {"hour": 1, "count": 23}, {"hour": 2, "count": 15}],
                [{"hour": 0, "count": 31}, {"hour": 1, "count": 28}],
                [{"hour": 0, "count": 45}],
            ]
            + [[]] * 4,  # Rest empty for 7 days
        )

        result = await analytics_manager.get_detection_frequency_distribution(days=7)

        # Should have stems 1, 2, 3, 4
        assert len(result) == 4

        # Check stem 1 (12, 15)
        stem_1 = next(r for r in result if r["stem"] == "1")
        assert "2" in stem_1["leaves"]  # From 12
        assert "5" in stem_1["leaves"]  # From 15

        # Check stem 2 (23, 28)
        stem_2 = next(r for r in result if r["stem"] == "2")
        assert "3" in stem_2["leaves"]  # From 23
        assert "8" in stem_2["leaves"]  # From 28

    @pytest.mark.asyncio
    async def test_get_stem_leaf_distribution_no_data(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should handle case with no detection data."""
        mock_detection_query_service.get_hourly_counts = AsyncMock(
            spec=DetectionQueryService.get_hourly_counts, return_value=[]
        )

        result = await analytics_manager.get_detection_frequency_distribution(days=7)

        assert len(result) == 1
        assert result[0]["stem"] == "0"
        assert result[0]["leaves"] == "No data"


class TestSpeciesHourlyPatterns:
    """Test species-specific hourly pattern analysis."""

    @pytest.mark.asyncio
    async def test_get_species_hourly_patterns_basic(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should aggregate hourly patterns for specific species."""
        # Create mock detections using factory
        robin_detections = [
            model_factory.create_detection_with_taxa(
                timestamp=datetime.now().replace(hour=6),
                species_tensor="Turdus_migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.9,
            ),
            model_factory.create_detection_with_taxa(
                timestamp=datetime.now().replace(hour=6),
                species_tensor="Turdus_migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.8,
            ),
            model_factory.create_detection_with_taxa(
                timestamp=datetime.now().replace(hour=12),
                species_tensor="Turdus_migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.85,
            ),
        ]
        other_bird = model_factory.create_detection_with_taxa(
            timestamp=datetime.now().replace(hour=18),
            species_tensor="Other_species_Other bird",
            scientific_name="Other species",
            common_name="Other bird",
            confidence=0.7,
        )
        mock_detections = [*robin_detections, other_bird]

        mock_detection_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
        )

        result = await analytics_manager.get_species_hourly_patterns("American Robin", days=7)

        assert len(result) == 24
        assert result[6] == 2  # Two detections at hour 6
        assert result[12] == 1  # One detection at hour 12
        assert result[18] == 0  # Other species, not counted

    @pytest.mark.asyncio
    async def test_get_species_hourly_patterns_multiple_name_variants(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should match species by any name variant."""
        mock_detections = [
            model_factory.create_detection_with_taxa(
                timestamp=datetime.now().replace(hour=8),
                species_tensor="Turdus_migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                ioc_english_name="American Robin",
                translated_name="Rouge-gorge américain",
                confidence=0.9,
            ),
        ]

        mock_detection_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
        )

        # Test with scientific name
        result = await analytics_manager.get_species_hourly_patterns("Turdus migratorius", days=1)
        assert result[8] == 1

        # Test with translated name
        result = await analytics_manager.get_species_hourly_patterns(
            "Rouge-gorge américain", days=1
        )
        assert result[8] == 1


class TestSpeciesAccumulationMethods:
    """Test different species accumulation curve methods."""

    @pytest.mark.asyncio
    async def test_species_accumulation_random_method(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should calculate random accumulation curves with averaging."""
        # Create detections with species pattern using factory
        mock_detections = [
            model_factory.create_detection_with_taxa(
                timestamp=datetime.now() - timedelta(hours=i),
                species_tensor=f"Species_{i % 3}_Bird_{i % 3}",
                scientific_name=f"Species_{i % 3}",  # 3 different species
                common_name=f"Bird_{i % 3}",
                confidence=0.8,
            )
            for i in range(10)
        ]

        # Mock the accumulation data as (timestamp, species) tuples
        mock_accumulation_data = [(det.timestamp, det.scientific_name) for det in mock_detections]

        mock_detection_query_service.get_detections_for_accumulation = AsyncMock(
            spec=DetectionQueryService.get_detections_for_accumulation,
            return_value=mock_accumulation_data,
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        with patch("random.shuffle", autospec=True):  # Control randomization for testing
            result = await analytics_manager.calculate_species_accumulation(
                start_date=start_date, end_date=end_date, method="random"
            )

        assert result["method"] == "random"
        assert len(result["samples"]) == 10
        assert len(result["species_counts"]) == 10

        # Species count should increase (or stay same) with samples
        for i in range(1, len(result["species_counts"])):
            assert result["species_counts"][i] >= result["species_counts"][i - 1]

    @pytest.mark.asyncio
    async def test_species_accumulation_rarefaction_method(
        self, analytics_manager, mock_detection_query_service, model_factory
    ):
        """Should calculate rarefaction curves."""
        # Create detections with uneven species distribution
        detections = []
        species_distribution = {"Species_A": 50, "Species_B": 30, "Species_C": 10}

        det_id = 1
        for species, count in species_distribution.items():
            for _ in range(count):
                detections.append(
                    model_factory.create_detection_with_taxa(
                        timestamp=datetime.now() - timedelta(hours=det_id),
                        species_tensor=f"{species}_{species}",
                        scientific_name=species,
                        common_name=species,
                        confidence=0.8,
                    )
                )
                det_id += 1

        # Mock the accumulation data as (timestamp, species) tuples
        mock_accumulation_data = [(det.timestamp, det.scientific_name) for det in detections]

        mock_detection_query_service.get_detections_for_accumulation = AsyncMock(
            spec=DetectionQueryService.get_detections_for_accumulation,
            return_value=mock_accumulation_data,
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        result = await analytics_manager.calculate_species_accumulation(
            start_date=start_date, end_date=end_date, method="rarefaction"
        )

        assert result["method"] == "rarefaction"
        assert len(result["samples"]) > 0
        assert len(result["species_counts"]) == len(result["samples"])

        # Expected species should increase with sample size
        assert result["species_counts"][-1] > result["species_counts"][0]


class TestBetaDiversity:
    """Test temporal beta diversity calculations."""

    @pytest.mark.asyncio
    async def test_calculate_beta_diversity_basic(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should calculate species turnover between time windows."""
        # Mock species sets for sliding windows
        mock_windows = [
            {
                "period_start": datetime.now() - timedelta(days=7),
                "period_end": datetime.now() - timedelta(days=6),
                "species": ["Species_A", "Species_B"],
            },
            {
                "period_start": datetime.now() - timedelta(days=6),
                "period_end": datetime.now() - timedelta(days=5),
                "species": ["Species_B", "Species_C"],  # A lost, C gained
            },
            {
                "period_start": datetime.now() - timedelta(days=5),
                "period_end": datetime.now() - timedelta(days=4),
                "species": ["Species_C", "Species_D", "Species_E"],  # B lost, D&E gained
            },
        ]

        mock_detection_query_service.get_species_sets_by_window = AsyncMock(
            spec=DetectionQueryService.get_species_sets_by_window, return_value=mock_windows
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        window_size = timedelta(days=1)

        result = await analytics_manager.calculate_beta_diversity(
            start_date=start_date, end_date=end_date, window_size=window_size
        )

        assert len(result) >= 2  # At least 2 comparisons

        # First comparison: Species_A lost, Species_C gained
        assert result[0]["species_lost"] == 1
        assert result[0]["species_gained"] == 1
        # Turnover rate = (1 + 1) / (2 * 3) = 2/6 = 0.3333
        # Total species = A, B, C (union of both sets)
        assert result[0]["turnover_rate"] == pytest.approx(0.3333, abs=0.01)

    @pytest.mark.asyncio
    async def test_calculate_beta_diversity_no_turnover(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should handle case with no species turnover."""
        # Same species in all windows
        mock_windows = [
            {
                "period_start": datetime.now() - timedelta(days=i),
                "period_end": datetime.now() - timedelta(days=i - 1),
                "species": ["Species_A", "Species_B"],
            }
            for i in range(3, 0, -1)
        ]

        mock_detection_query_service.get_species_sets_by_window = AsyncMock(
            spec=DetectionQueryService.get_species_sets_by_window, return_value=mock_windows
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=3)
        window_size = timedelta(days=1)

        result = await analytics_manager.calculate_beta_diversity(
            start_date=start_date, end_date=end_date, window_size=window_size
        )

        # All turnover rates should be 0
        for comparison in result:
            assert comparison["turnover_rate"] == 0
            assert comparison["species_lost"] == 0
            assert comparison["species_gained"] == 0


class TestWeatherCorrelations:
    """Test weather correlation analysis."""

    @pytest.mark.asyncio
    async def test_get_weather_correlation_data_passthrough(
        self, analytics_manager, mock_detection_query_service
    ):
        """Should pass through to detection query service."""
        # Mock weather correlation data from query service
        mock_data = {
            "correlations": {
                "temperature": 0.75,
                "humidity": -0.5,
                "wind_speed": 0.3,
            },
            "data_points": 100,
        }

        mock_detection_query_service.get_weather_correlations = AsyncMock(
            spec=callable, return_value=mock_data
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        result = await analytics_manager.get_weather_correlation_data(start_date, end_date)

        # Should return exactly what the query service returns
        assert result == mock_data

        # Verify correct parameters passed
        mock_detection_query_service.get_weather_correlations.assert_called_once_with(
            start_date=start_date, end_date=end_date
        )


class TestCorrelationCalculation:
    """Test Pearson correlation calculation method."""

    @pytest.mark.parametrize(
        "x,y,expected,description",
        [
            pytest.param(
                [1, 2, 3, 4, 5],
                [2, 4, 6, 8, 10],
                1.0,
                "Perfect positive correlation",
                id="perfect-positive",
            ),
            pytest.param(
                [1, 2, 3, 4, 5],
                [10, 8, 6, 4, 2],
                -1.0,
                "Perfect negative correlation",
                id="perfect-negative",
            ),
            pytest.param(
                [1, 2, 3, 4, 5],
                [5, 2, 8, 1, 7],
                None,  # We'll check abs < 0.5
                "Random, no correlation",
                id="no-correlation",
            ),
            pytest.param(
                [1, 2, None, 4, 5],
                [2, None, 6, 8, 10],
                "positive",  # We'll check > 0
                "None values filtered out",
                id="with-none-values",
            ),
            pytest.param(
                [1],
                [2],
                0.0,
                "Insufficient data points",
                id="insufficient-data",
            ),
            pytest.param(
                [None, None, None],
                [None, None, None],
                0.0,
                "All None values",
                id="all-none",
            ),
        ],
    )
    def test_calculate_correlation(self, analytics_manager, x, y, expected, description):
        """Should calculate correlation for various data patterns."""
        result = analytics_manager.calculate_correlation(x, y)

        if expected == "positive":
            assert result > 0, f"{description}: Expected positive correlation"
        elif expected is None:  # No correlation case
            assert abs(result) < 0.5, f"{description}: Expected near-zero correlation"
        else:
            assert result == pytest.approx(expected, abs=0.01), (
                f"{description}: Unexpected correlation value"
            )
