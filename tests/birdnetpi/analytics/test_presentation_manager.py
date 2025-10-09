"""Unit tests for PresentationManager."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.detections.models import Detection


@pytest.fixture
def mock_analytics_manager():
    """Create a mock AnalyticsManager."""
    return MagicMock(spec=AnalyticsManager)


@pytest.fixture
def mock_config():
    """Create a mock BirdNETConfig."""
    # Create actual instance with test values

    config = BirdNETConfig(species_confidence_threshold=0.7, timezone="UTC")
    return config


@pytest.fixture
def presentation_manager(mock_analytics_manager, detection_query_service_factory, mock_config):
    """Create a PresentationManager with mocked dependencies."""
    return PresentationManager(
        mock_analytics_manager, detection_query_service_factory(), mock_config
    )


@pytest.fixture
def sample_detections():
    """Create sample detection objects for testing."""
    return [
        Detection(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2024, 1, 1, 10, 30, 0),
        ),
        Detection(
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            confidence=0.88,
            timestamp=datetime(2024, 1, 1, 11, 15, 0),
        ),
        Detection(
            species_tensor="Unknown species",
            scientific_name="Unknown species",
            common_name=None,  # No common name
            confidence=0.65,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
    ]


class TestLandingPageData:
    """Test landing page data preparation."""

    @pytest.mark.asyncio
    async def test_get_landing_page_data(
        self,
        presentation_manager,
        mock_analytics_manager,
        detection_query_service_factory,
        sample_detections,
    ):
        """Should assemble complete landing page data correctly."""
        # Configure analytics manager mocks (as async)
        mock_analytics_manager.get_dashboard_summary = AsyncMock(
            spec=AnalyticsManager.get_dashboard_summary,
            return_value={
                "species_total": 150,
                "detections_today": 25,
                "species_week": 35,
                "storage_gb": 5.5,
                "hours_monitored": 120.0,
                "confidence_threshold": 0.7,
            },
        )

        mock_analytics_manager.get_species_frequency_analysis = AsyncMock(
            spec=AnalyticsManager.get_species_frequency_analysis,
            return_value=[
                {"name": "American Robin", "count": 50, "percentage": 40.0, "category": "common"},
                {
                    "name": "Northern Cardinal",
                    "count": 30,
                    "percentage": 24.0,
                    "category": "regular",
                },
                {"name": "Blue Jay", "count": 20, "percentage": 16.0, "category": "regular"},
            ],
        )

        mock_analytics_manager.get_temporal_patterns = AsyncMock(
            spec=AnalyticsManager.get_temporal_patterns,
            return_value={
                "hourly_distribution": [
                    0,
                    0,
                    0,
                    0,
                    0,
                    10,
                    15,
                    25,
                    20,
                    18,
                    12,
                    8,
                    5,
                    3,
                    2,
                    1,
                    1,
                    2,
                    4,
                    6,
                    5,
                    3,
                    2,
                    0,
                ],
                "peak_hour": 7,
                "periods": {
                    "night_early": 0,
                    "dawn": 50,
                    "morning": 63,
                    "afternoon": 11,
                    "evening": 12,
                    "night_late": 14,
                },
            },
        )

        # Mock detection query service method
        mock_detection_query_service = detection_query_service_factory(
            query_detections=sample_detections
        )
        presentation_manager.detection_query_service = mock_detection_query_service

        mock_analytics_manager.get_detection_scatter_data = AsyncMock(
            spec=AnalyticsManager.get_detection_scatter_data,
            return_value=[
                {
                    "time": 6.25,
                    "confidence": 0.95,
                    "species": "American Robin",
                    "frequency_category": "common",
                },
                {
                    "time": 7.5,
                    "confidence": 0.88,
                    "species": "Northern Cardinal",
                    "frequency_category": "regular",
                },
            ],
        )

        # Get landing page data
        data = await presentation_manager.get_landing_page_data()

        # Verify structure (Pydantic model attributes)
        assert hasattr(data, "metrics")
        assert hasattr(data, "detection_log")
        assert hasattr(data, "species_frequency")
        assert hasattr(data, "hourly_distribution")
        assert hasattr(data, "visualization_data")

        # Verify metrics formatting
        assert data.metrics.species_detected == "150"
        assert data.metrics.detections_today == "25"
        assert data.metrics.species_week == "35"
        assert data.metrics.storage == "5.5 GB"
        assert data.metrics.hours == "120"
        assert data.metrics.threshold == "≥0.70"

        # Verify detection log
        assert len(data.detection_log) == 3
        assert data.detection_log[0].time == "10:30"
        assert data.detection_log[0].common_name == "American Robin"
        assert data.detection_log[0].confidence == "95%"

        # Verify species frequency (limited to 12)
        assert len(data.species_frequency) == 3
        assert data.species_frequency[0].name == "American Robin"
        assert data.species_frequency[0].count == 50
        assert data.species_frequency[0].bar_width == "100%"  # Highest count

        # Verify hourly distribution
        assert data.hourly_distribution == [
            0,
            0,
            0,
            0,
            0,
            10,
            15,
            25,
            20,
            18,
            12,
            8,
            5,
            3,
            2,
            1,
            1,
            2,
            4,
            6,
            5,
            3,
            2,
            0,
        ]

        # Verify visualization data
        assert len(data.visualization_data) == 2
        assert data.visualization_data[0].x == 6.25
        assert data.visualization_data[0].y == 0.95
        assert data.visualization_data[0].color == "#2e7d32"  # common = green


class TestFormatting:
    """Test individual formatting methods."""

    def test_format_metrics(self, presentation_manager):
        """Should metrics formatting."""
        summary = {
            "species_total": 1250,
            "detections_today": 42,
            "species_week": 18,
            "storage_gb": 12.345,
            "hours_monitored": 168.5,
            "confidence_threshold": 0.85,
        }

        formatted = presentation_manager._format_metrics(summary)

        assert formatted.species_detected == "1,250"
        assert formatted.detections_today == "42"
        assert formatted.species_week == "18"
        assert formatted.storage == "12.3 GB"
        assert formatted.hours == "168"
        assert formatted.threshold == "≥0.85"

    def test_format_detection_log(self, presentation_manager, sample_detections):
        """Should detection log formatting."""
        formatted = presentation_manager._format_detection_log(sample_detections)

        assert len(formatted) == 3

        # Check first detection
        assert formatted[0].time == "10:30"
        assert formatted[0].common_name == "American Robin"
        assert formatted[0].confidence == "95%"

        # Check detection with no common name
        assert formatted[2].common_name == "Unknown species"  # Falls back to scientific name
        assert formatted[2].confidence == "65%"

    def test_format_detection_log_empty(self, presentation_manager):
        """Should detection log formatting with empty list."""
        formatted = presentation_manager._format_detection_log([])
        assert formatted == []

    def test_format_species_list(self, presentation_manager):
        """Should species list formatting."""
        frequency_data = [
            {"name": "Species A", "count": 100, "percentage": 50.0, "category": "common"},
            {"name": "Species B", "count": 60, "percentage": 30.0, "category": "regular"},
            {"name": "Species C", "count": 40, "percentage": 20.0, "category": "uncommon"},
        ]

        formatted = presentation_manager._format_species_list(frequency_data)

        assert len(formatted) == 3

        # First species should have 100% bar width (highest count)
        assert formatted[0].name == "Species A"
        assert formatted[0].count == 100
        assert formatted[0].bar_width == "100%"

        # Second species bar width relative to first
        assert formatted[1].bar_width == "60%"

        # Third species bar width relative to first
        assert formatted[2].bar_width == "40%"

    def test_format_species_list_empty(self, presentation_manager):
        """Should species list formatting with empty data."""
        formatted = presentation_manager._format_species_list([])
        assert formatted == []

    def test_format_scatter_data(self, presentation_manager):
        """Should scatter plot data formatting."""
        scatter_data = [
            {"time": 6.5, "confidence": 0.95, "species": "Robin", "frequency_category": "common"},
            {
                "time": 12.25,
                "confidence": 0.75,
                "species": "Cardinal",
                "frequency_category": "regular",
            },
            {
                "time": 18.75,
                "confidence": 0.60,
                "species": "Sparrow",
                "frequency_category": "uncommon",
            },
            {
                "time": 20.0,
                "confidence": 0.55,
                "species": "Unknown",
                "frequency_category": "rare",
            },  # Unknown category
        ]

        formatted = presentation_manager._format_scatter_data(scatter_data)

        assert len(formatted) == 4

        # Check color mapping for known categories
        assert formatted[0].color == "#2e7d32"  # common = green
        assert formatted[1].color == "#f57c00"  # regular = orange
        assert formatted[2].color == "#c62828"  # uncommon = red
        assert formatted[3].color == "#666"  # unknown category = gray

        # Check data transformation
        assert formatted[0].x == 6.5
        assert formatted[0].y == 0.95
        assert formatted[0].species == "Robin"


class TestAPIFormatting:
    """Should format API responses correctly."""

    def test_format_api_response_success(self, presentation_manager):
        """Should successful API response formatting."""
        data = {"result": "test", "count": 42}

        with patch("birdnetpi.analytics.presentation.datetime", autospec=True) as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            response = presentation_manager.format_api_response(data)

        assert response.status == "success"
        assert response.timestamp == "2024-01-01T12:00:00"
        assert response.data == data

    def test_format_api_response_error(self, presentation_manager):
        """Should error API response formatting."""
        error_data = {"error": "Not found"}

        with patch("birdnetpi.analytics.presentation.datetime", autospec=True) as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            response = presentation_manager.format_api_response(error_data, status="error")

        assert response.status == "error"
        assert response.timestamp == "2024-01-01T12:00:00"
        assert response.data == error_data

    def test_format_api_response_custom_status(self, presentation_manager):
        """Should API response with custom status."""
        data = {"message": "Processing"}

        response = presentation_manager.format_api_response(data, status="pending")

        assert response.status == "pending"
        assert response.data == data
        assert hasattr(response, "timestamp")


class TestSparklineGeneration:
    """Test sparkline data generation."""

    @pytest.mark.asyncio
    async def test_generate_sparkline_data(self, presentation_manager, mock_analytics_manager):
        """Should sparkline data generation for species trends."""
        # Mock the hourly patterns method
        mock_analytics_manager.get_species_hourly_patterns = AsyncMock(
            spec=AnalyticsManager.get_species_hourly_patterns,
            side_effect=[
                [
                    5,
                    10,
                    15,
                    12,
                    8,
                    20,
                    25,
                    10,
                    5,
                    3,
                    2,
                    1,
                    0,
                    0,
                    1,
                    2,
                    3,
                    5,
                    8,
                    10,
                    12,
                    15,
                    10,
                    8,
                ],  # 24 hours
                [
                    3,
                    5,
                    4,
                    6,
                    7,
                    8,
                    9,
                    10,
                    8,
                    6,
                    5,
                    4,
                    3,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    8,
                    7,
                    6,
                ],  # 24 hours
            ],
        )

        top_species = [
            {
                "id": 1,
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "count": 100,
            },
            {
                "id": 2,
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "count": 50,
            },
        ]

        result = await presentation_manager._generate_sparkline_data(top_species, "week")

        # Check that hourly patterns were requested
        assert mock_analytics_manager.get_species_hourly_patterns.call_count == 2

        # Check result structure
        assert "1-spark" in result  # Using species ID
        assert "2-spark" in result
        assert len(result["1-spark"]) == 24  # 24 hours
        assert len(result["2-spark"]) == 24

    @pytest.mark.asyncio
    async def test_generate_sparkline_data_empty(
        self, presentation_manager, mock_analytics_manager
    ):
        """Should handle sparkline generation with no species."""
        result = await presentation_manager._generate_sparkline_data([], "week")
        assert result == {}


class TestDiversityFormatting:
    """Test diversity data formatting methods."""

    def test_format_diversity_timeline(self, presentation_manager):
        """Should formatting diversity timeline data."""
        # Data structure matching what AnalyticsManager returns
        data = [
            {
                "period": "2024-01-01",
                "shannon": 2.5,
                "simpson": 0.85,
                "richness": 10,
                "evenness": 0.75,
                "total_detections": 50,
            },
            {
                "period": "2024-01-02",
                "shannon": 2.7,
                "simpson": 0.87,
                "richness": 12,
                "evenness": 0.78,
                "total_detections": 60,
            },
            {
                "period": "2024-01-03",
                "shannon": 2.6,
                "simpson": 0.86,
                "richness": 11,
                "evenness": 0.76,
                "total_detections": 55,
            },
        ]

        formatted = presentation_manager._format_diversity_timeline(data)

        assert "periods" in formatted
        assert "shannon" in formatted
        assert "simpson" in formatted
        assert "richness" in formatted
        assert "evenness" in formatted
        assert "total_detections" in formatted
        assert formatted["periods"] == ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert formatted["shannon"] == [2.5, 2.7, 2.6]
        assert formatted["simpson"] == [0.85, 0.87, 0.86]
        assert formatted["richness"] == [10, 12, 11]
        assert formatted["evenness"] == [0.75, 0.78, 0.76]
        assert formatted["total_detections"] == [50, 60, 55]

    def test_format_diversity_comparison(self, presentation_manager):
        """Should formatting diversity comparison data."""
        data = {
            "period1": {"shannon": 2.3, "simpson": 0.82, "species_count": 12},
            "period2": {"shannon": 2.5, "simpson": 0.85, "species_count": 15},
            "changes": {"shannon": 0.2, "simpson": 0.03, "species_count": 3},
        }

        formatted = presentation_manager._format_diversity_comparison(data)

        assert "period1_metrics" in formatted
        assert "period2_metrics" in formatted
        assert "changes" in formatted
        assert formatted["period1_metrics"]["shannon"] == 2.3
        assert formatted["period2_metrics"]["shannon"] == 2.5
        # Check formatted changes
        assert formatted["changes"]["shannon"]["value"] == 0.2
        assert formatted["changes"]["shannon"]["trend"] == "up"
        assert formatted["changes"]["species_count"]["value"] == 3

    def test_format_accumulation_curve(self, presentation_manager):
        """Should formatting species accumulation curve data."""
        # Data structure matching what AnalyticsManager returns
        data = {
            "samples": [1, 2, 3, 4, 5, 6, 7, 8],
            "species_counts": [1, 3, 5, 7, 9, 10, 11, 12],
            "method": "collector",
        }

        formatted = presentation_manager._format_accumulation_curve(data)

        assert "samples" in formatted
        assert "species_counts" in formatted
        assert "method" in formatted
        assert "total_samples" in formatted
        assert "total_species" in formatted
        assert len(formatted["samples"]) == 8
        assert formatted["species_counts"][-1] == 12
        assert formatted["total_samples"] == 8
        assert formatted["total_species"] == 12


class TestWeatherFormatting:
    """Test weather correlation formatting."""

    def test_format_weather_correlations(self, presentation_manager):
        """Should formatting weather correlation data."""
        # Data structure with raw arrays as expected by implementation
        data = {
            "hours": ["00:00", "01:00", "02:00", "03:00"],
            "detection_counts": [5, 10, 15, 20],
            "temperature": [15.5, 16.0, 17.2, 18.5],
            "humidity": [65, 70, 75, 80],
            "wind_speed": [5.0, 3.5, 2.0, 4.5],
            "precipitation": [0.0, 0.0, 0.5, 1.0],
        }

        formatted = presentation_manager._format_weather_correlations(data)

        assert "hours" in formatted
        assert "detection_counts" in formatted
        assert "weather_variables" in formatted
        assert "correlations" in formatted

        # Check that raw data is preserved
        assert formatted["hours"] == data["hours"]
        assert formatted["detection_counts"] == data["detection_counts"]

        # Check weather variables structure
        assert "temperature" in formatted["weather_variables"]
        assert "humidity" in formatted["weather_variables"]
        assert "wind_speed" in formatted["weather_variables"]
        assert "precipitation" in formatted["weather_variables"]
        assert formatted["weather_variables"]["temperature"] == data["temperature"]
        assert formatted["weather_variables"]["humidity"] == data["humidity"]


class TestPeriodCalculations:
    """Test period calculation utilities."""

    def test_calculate_period_range(self, presentation_manager):
        """Should period range calculations."""
        # Test week period
        start, label = presentation_manager._calculate_period_range("week")
        assert start is not None
        assert label == "This Week"

        # Test month period
        start, label = presentation_manager._calculate_period_range("month")
        assert start is not None
        assert label == "This Month"

        # Test year period
        start, label = presentation_manager._calculate_period_range("year")
        assert start is not None
        assert label == "This Year"

    def test_get_resolution_for_period(self, presentation_manager):
        """Should resolution selection for different periods."""
        assert presentation_manager._get_resolution_for_period("day") == "hourly"
        assert presentation_manager._get_resolution_for_period("week") == "daily"
        assert presentation_manager._get_resolution_for_period("month") == "daily"
        assert presentation_manager._get_resolution_for_period("year") == "weekly"
        assert presentation_manager._get_resolution_for_period("season") == "weekly"

    def test_get_window_size_for_period(self, presentation_manager):
        """Should window size calculation for periods."""
        assert presentation_manager._get_window_size_for_period("day") == timedelta(hours=6)
        assert presentation_manager._get_window_size_for_period("week") == timedelta(days=1)
        assert presentation_manager._get_window_size_for_period("month") == timedelta(days=5)
        assert presentation_manager._get_window_size_for_period("season") == timedelta(days=15)
        assert presentation_manager._get_window_size_for_period("year") == timedelta(days=60)

    def test_get_days_for_period(self, presentation_manager):
        """Should day count for different periods."""
        assert presentation_manager._get_days_for_period("day") == 1
        assert presentation_manager._get_days_for_period("week") == 7
        assert presentation_manager._get_days_for_period("month") == 30
        assert presentation_manager._get_days_for_period("year") == 365

    def test_get_intensity_class(self, presentation_manager):
        """Should intensity classification."""
        assert presentation_manager._get_intensity_class(0.0) == "very-low"
        assert presentation_manager._get_intensity_class(0.15) == "very-low"
        assert presentation_manager._get_intensity_class(0.35) == "low"
        assert presentation_manager._get_intensity_class(0.45) == "medium"
        assert presentation_manager._get_intensity_class(0.75) == "high"
        assert presentation_manager._get_intensity_class(0.95) == "very-high"


class TestSpeciesFrequencyFormatting:
    """Test species frequency formatting."""

    def test_format_species_frequency(self, presentation_manager):
        """Should species frequency data formatting."""
        species_summary = [
            {
                "common_name": "American Robin",
                "count": 100,
                "scientific_name": "Turdus migratorius",
            },
            {
                "common_name": "Northern Cardinal",
                "count": 75,
                "scientific_name": "Cardinalis cardinalis",
            },
            {"common_name": "Blue Jay", "count": 50, "scientific_name": "Cyanocitta cristata"},
            {"common_name": "Sparrow", "count": 25, "scientific_name": "Passer domesticus"},
        ]

        formatted = presentation_manager._format_species_frequency(species_summary, "week")

        assert len(formatted) <= 10  # Limited to top 10 species
        assert all("name" in s for s in formatted)
        assert all("count" in s for s in formatted)
        assert all("week" in s for s in formatted)
        assert all("month" in s for s in formatted)
        assert all("trend" in s for s in formatted)

        # Check first species
        if formatted:
            assert formatted[0]["name"] == "American Robin"
            assert formatted[0]["count"] == 100
            assert formatted[0]["week"] == 100  # Count shown for week period

    def test_format_top_species(self, presentation_manager):
        """Should top species formatting."""
        species_summary = [
            {"common_name": "Robin", "count": 150, "scientific_name": "Turdus migratorius"},
            {"common_name": "Cardinal", "count": 100, "scientific_name": "Cardinalis cardinalis"},
            {"common_name": "Blue Jay", "count": 75, "scientific_name": "Cyanocitta cristata"},
            {"common_name": "Sparrow", "count": 60, "scientific_name": "Passer domesticus"},
            {"common_name": "Crow", "count": 50, "scientific_name": "Corvus brachyrhynchos"},
            {"common_name": "Finch", "count": 40, "scientific_name": "Fringilla coelebs"},
            {"common_name": "Dove", "count": 30, "scientific_name": "Zenaida macroura"},
        ]

        formatted = presentation_manager._format_top_species(species_summary)

        assert len(formatted) <= 6  # Limited to top 6
        assert all("id" in s for s in formatted)
        assert all("common_name" in s for s in formatted)
        assert all("scientific_name" in s for s in formatted)
        assert all("count" in s for s in formatted)

        # Verify first species
        assert formatted[0]["count"] == 150
        assert formatted[0]["common_name"] == "Robin"
        assert formatted[0]["id"] == "species-0"


class TestChartFormattingMethods:
    """Test chart-specific formatting methods."""

    def test_format_diversity_timeline(self, presentation_manager):
        """Should format diversity timeline data for charts."""
        timeline_data = [
            {
                "period": "2024-01-01",
                "shannon": 2.3,
                "simpson": 0.85,
                "richness": 10,
                "evenness": 0.75,
                "total_detections": 50,
            },
            {
                "period": "2024-01-02",
                "shannon": 2.5,
                "simpson": 0.88,
                "richness": 12,
                "evenness": 0.78,
                "total_detections": 60,
            },
            {
                "period": "2024-01-03",
                "shannon": 2.7,
                "simpson": 0.90,
                "richness": 15,
                "evenness": 0.80,
                "total_detections": 75,
            },
        ]

        result = presentation_manager._format_diversity_timeline(timeline_data)

        assert "periods" in result
        assert "shannon" in result
        assert "simpson" in result
        assert "richness" in result
        assert "evenness" in result
        assert "total_detections" in result
        assert len(result["periods"]) == 3
        assert result["shannon"] == [2.3, 2.5, 2.7]
        assert result["richness"] == [10, 12, 15]

    def test_format_diversity_comparison(self, presentation_manager):
        """Should format diversity comparison data."""
        comparison_data = {
            "period1": {"shannon": 2.9, "simpson": 0.85, "richness": 20},
            "period2": {"shannon": 3.2, "simpson": 0.90, "richness": 25},
            "changes": {"shannon": 0.3, "simpson": 0.05, "richness": 5},
        }

        result = presentation_manager._format_diversity_comparison(comparison_data)

        assert "period1_metrics" in result
        assert "period2_metrics" in result
        assert "changes" in result
        assert result["period1_metrics"]["shannon"] == 2.9
        assert result["period2_metrics"]["richness"] == 25

    def test_format_accumulation_curve(self, presentation_manager):
        """Should format species accumulation curve data."""
        accumulation_data = {
            "samples": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "species_counts": [5, 8, 10],
            "method": "rarefaction",
        }

        result = presentation_manager._format_accumulation_curve(accumulation_data)

        assert "samples" in result
        assert "species_counts" in result
        assert "method" in result
        assert "total_samples" in result
        assert "total_species" in result
        assert result["total_samples"] == 3
        assert result["total_species"] == 10

    def test_format_similarity_matrix(self, presentation_manager):
        """Should format similarity matrix data."""
        matrix_data = {
            "labels": ["Week 1", "Week 2", "Week 3"],
            "matrix": [[1.0, 0.8, 0.6], [0.8, 1.0, 0.7], [0.6, 0.7, 1.0]],
            "index_type": "jaccard",
        }

        result = presentation_manager._format_similarity_matrix(matrix_data)

        assert "labels" in result
        assert "matrix" in result
        assert "index_type" in result
        assert len(result["labels"]) == 3
        assert len(result["matrix"]) == 3
        # Check formatted matrix structure
        assert "value" in result["matrix"][0][0]
        assert result["matrix"][0][0]["value"] == 100.0  # 1.0 * 100

    def test_format_beta_diversity(self, presentation_manager):
        """Should format beta diversity data."""
        beta_data = [
            {
                "period_start": "2024-01-01",
                "turnover_rate": 0.3,
                "species_gained": 5,
                "species_lost": 2,
                "total_species": 25,
            },
            {
                "period_start": "2024-02-01",
                "turnover_rate": 0.4,
                "species_gained": 7,
                "species_lost": 3,
                "total_species": 29,
            },
        ]

        result = presentation_manager._format_beta_diversity(beta_data)

        assert "periods" in result
        assert "turnover_rates" in result
        assert "species_gained" in result
        assert "species_lost" in result
        assert "total_species" in result
        assert len(result["periods"]) == 2
        assert result["turnover_rates"] == [0.3, 0.4]
        assert result["species_gained"] == [5, 7]

    def test_format_weather_correlations(self, presentation_manager, mocker):
        """Should format weather correlation data."""
        # Mock analytics manager's calculate_correlation method
        mock_calculate = mocker.patch.object(
            presentation_manager.analytics_manager, "calculate_correlation"
        )
        mock_calculate.side_effect = [0.65, -0.45, -0.20]  # Return values for each call

        weather_data = {
            "hours": [0, 6, 12, 18, 24],
            "detection_counts": [10, 15, 20, 25, 30],
            "temperature": [15, 18, 20, 22, 25],
            "humidity": [60, 65, 70, 75, 80],
            "wind_speed": [5, 10, 15, 20, 25],
            "precipitation": [0, 0.1, 0.2, 0.5, 1.0],
        }

        result = presentation_manager._format_weather_correlations(weather_data)

        assert "hours" in result
        assert "detection_counts" in result
        assert "weather_variables" in result
        assert "correlations" in result

        # Check weather variables structure
        assert "temperature" in result["weather_variables"]
        assert "humidity" in result["weather_variables"]
        assert "wind_speed" in result["weather_variables"]
        assert "precipitation" in result["weather_variables"]

        # Check correlations were calculated
        assert mock_calculate.call_count == 3
        assert result["correlations"]["temperature"] == 0.65
        assert result["correlations"]["humidity"] == -0.45
        assert result["correlations"]["wind_speed"] == -0.20


class TestUtilityMethods:
    """Test utility methods for date and period calculations."""

    def test_calculate_analysis_period_dates(self, presentation_manager):
        """Should calculate correct date ranges for analysis periods."""
        # Test day period
        start, end = presentation_manager._calculate_analysis_period_dates("day")
        assert (end - start).days == 1

        # Test week period
        start, end = presentation_manager._calculate_analysis_period_dates("week")
        assert (end - start).days == 7

        # Test month period
        start, end = presentation_manager._calculate_analysis_period_dates("month")
        assert 28 <= (end - start).days <= 31

        # Test year period
        start, end = presentation_manager._calculate_analysis_period_dates("year")
        assert 365 <= (end - start).days <= 366
