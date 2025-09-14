"""Tests for analysis API routes that handle progressive loading of analysis data."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.analysis_api_routes import router


@pytest.fixture
def client():
    """Create test client with analysis API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override PresentationManager with mock
    mock_presentation_manager = MagicMock(spec=PresentationManager)
    mock_analytics_manager = MagicMock()
    mock_presentation_manager.analytics_manager = mock_analytics_manager

    container.presentation_manager.override(mock_presentation_manager)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.analysis_api_routes"])
    app.container = container  # type: ignore[attr-defined]

    # Include the router (router already has /api/analysis prefix)
    app.include_router(router)

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_presentation_manager = mock_presentation_manager  # type: ignore[attr-defined]
    client.mock_analytics_manager = mock_analytics_manager  # type: ignore[attr-defined]

    return client


class TestAnalysisAPIRoutes:
    """Test analysis API endpoints for progressive loading."""

    def test_get_diversity_analysis(self, client):
        """Should return diversity analysis data."""
        # Setup mock data
        mock_diversity_data = {
            "periods": ["2025-01-01", "2025-01-02"],
            "shannon": [2.3, 2.5],
            "simpson": [0.8, 0.85],
            "richness": [15, 18],
            "evenness": [0.7, 0.75],
        }

        formatted_diversity = {
            "periods": ["2025-01-01", "2025-01-02"],
            "shannon": [2.3, 2.5],
            "simpson": [0.8, 0.85],
            "richness": [15, 18],
            "evenness": [0.7, 0.75],
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_presentation_manager._get_resolution_for_period.return_value = "day"
        client.mock_analytics_manager.calculate_diversity_timeline = AsyncMock(
            return_value=mock_diversity_data
        )
        client.mock_presentation_manager._format_diversity_timeline.return_value = (
            formatted_diversity
        )

        # Make request
        response = client.get("/api/analysis/diversity?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "diversity" in data
        assert data["diversity"]["periods"] == ["2025-01-01", "2025-01-02"]
        assert data["diversity"]["shannon"] == [2.3, 2.5]

    def test_get_diversity_with_comparison(self, client):
        """Should return diversity analysis with comparison data."""
        # Setup mock data
        mock_diversity_data = {
            "periods": ["2025-01-01"],
            "shannon": [2.3],
            "simpson": [0.8],
            "richness": [15],
            "evenness": [0.7],
        }

        mock_comparison_data = {
            "period1": {"shannon": 2.3, "simpson": 0.8},
            "period2": {"shannon": 2.1, "simpson": 0.75},
            "changes": {
                "shannon_change": {"value": 0.2, "trend": "up"},
                "simpson_change": {"value": 0.05, "trend": "up"},
            },
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.side_effect = [
            (datetime(2025, 1, 1), datetime(2025, 1, 31)),
            (datetime(2024, 12, 1), datetime(2024, 12, 31)),
        ]
        client.mock_presentation_manager._get_resolution_for_period.return_value = "day"
        client.mock_analytics_manager.calculate_diversity_timeline = AsyncMock(
            return_value=mock_diversity_data
        )
        client.mock_analytics_manager.compare_period_diversity = AsyncMock(
            return_value=mock_comparison_data
        )
        client.mock_presentation_manager._format_diversity_timeline.return_value = (
            mock_diversity_data
        )
        client.mock_presentation_manager._format_diversity_comparison.return_value = (
            mock_comparison_data
        )

        # Make request
        response = client.get("/api/analysis/diversity?period=30d&comparison=previous")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "diversity" in data
        assert "diversity_comparison" in data
        assert data["diversity_comparison"]["changes"]["shannon_change"]["trend"] == "up"

    def test_get_accumulation_analysis(self, client):
        """Should return species accumulation curve data."""
        # Setup mock data
        mock_accumulation_data = {
            "samples": list(range(100)),
            "species_counts": list(range(1, 101)),
            "total_species": 100,
            "total_samples": 100,
            "method": "collector",
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_analytics_manager.calculate_species_accumulation = AsyncMock(
            return_value=mock_accumulation_data
        )
        client.mock_presentation_manager._format_accumulation_curve.return_value = (
            mock_accumulation_data
        )

        # Make request
        response = client.get("/api/analysis/accumulation?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "accumulation" in data
        assert data["accumulation"]["total_species"] == 100
        assert data["accumulation"]["method"] == "collector"

    def test_get_similarity_analysis(self, client):
        """Should return community similarity matrix data."""
        # Setup mock data
        mock_similarity_data = {
            "labels": ["Week 1", "Week 2", "Week 3"],
            "matrix": [
                [{"value": 1.0, "display": "100", "intensity": "very-high"}],
                [{"value": 0.7, "display": "70", "intensity": "high"}],
                [{"value": 0.5, "display": "50", "intensity": "medium"}],
            ],
            "index_type": "jaccard",
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_presentation_manager._generate_similarity_periods.return_value = [
            (datetime(2025, 1, 1), datetime(2025, 1, 7)),
            (datetime(2025, 1, 8), datetime(2025, 1, 14)),
            (datetime(2025, 1, 15), datetime(2025, 1, 21)),
        ]
        client.mock_analytics_manager.calculate_community_similarity = AsyncMock(
            return_value=mock_similarity_data
        )
        client.mock_presentation_manager._format_similarity_matrix.return_value = (
            mock_similarity_data
        )

        # Make request
        response = client.get("/api/analysis/similarity?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "similarity" in data
        assert data["similarity"]["index_type"] == "jaccard"
        assert len(data["similarity"]["labels"]) == 3

    def test_get_beta_diversity(self, client):
        """Should return beta diversity analysis data."""
        # Setup mock data
        mock_beta_data = {
            "periods": ["2025-01-01", "2025-01-02"],
            "turnover_rates": [0.2, 0.3],
            "species_gained": [5, 3],
            "species_lost": [2, 4],
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_presentation_manager._get_window_size_for_period.return_value = 7
        client.mock_analytics_manager.calculate_beta_diversity = AsyncMock(
            return_value=mock_beta_data
        )
        client.mock_presentation_manager._format_beta_diversity.return_value = mock_beta_data

        # Make request
        response = client.get("/api/analysis/beta?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "beta_diversity" in data
        assert data["beta_diversity"]["turnover_rates"] == [0.2, 0.3]

    def test_get_weather_correlations(self, client):
        """Should return weather correlation analysis data."""
        # Setup mock data
        mock_weather_data = {
            "correlations": {
                "temperature": 0.65,
                "humidity": -0.45,
                "wind_speed": -0.25,
            },
            "weather_variables": {
                "temperature": [20, 22, 24],
                "humidity": [60, 65, 70],
                "wind_speed": [5, 10, 15],
            },
            "detection_counts": [100, 120, 80],
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_analytics_manager.get_weather_correlation_data = AsyncMock(
            return_value=mock_weather_data
        )
        client.mock_presentation_manager._format_weather_correlations.return_value = (
            mock_weather_data
        )

        # Make request
        response = client.get("/api/analysis/weather?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "weather" in data
        assert data["weather"]["correlations"]["temperature"] == 0.65
        assert data["weather"]["correlations"]["humidity"] == -0.45

    def test_get_temporal_patterns(self, client):
        """Should return temporal pattern analysis data."""
        # Setup mock data
        mock_temporal_data = {
            "hourly_distribution": list(range(24)),
            "peak_hour": 6,
            "periods": ["dawn", "morning", "afternoon", "evening", "night"],
        }
        mock_heatmap_data = [[0] * 24 for _ in range(7)]

        # Configure mocks
        client.mock_analytics_manager.get_temporal_patterns = AsyncMock(
            return_value=mock_temporal_data
        )
        client.mock_analytics_manager.get_aggregate_hourly_pattern = AsyncMock(
            return_value=mock_heatmap_data
        )
        client.mock_presentation_manager._get_days_for_period.return_value = 30

        # Make request
        response = client.get("/api/analysis/patterns?period=30d")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "temporal_patterns" in data
        assert data["temporal_patterns"]["peak_hour"] == 6
        assert "heatmap" in data["temporal_patterns"]
        assert len(data["temporal_patterns"]["heatmap"]) == 7

    def test_error_handling(self, client):
        """Should handle errors gracefully and return 500 status."""
        # Configure mock to raise exception
        client.mock_presentation_manager._calculate_analysis_period_dates.side_effect = Exception(
            "Database error"
        )

        # Make request
        response = client.get("/api/analysis/diversity?period=30d")

        # Verify error response
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Database error" in data["detail"]

    def test_different_periods(self, client):
        """Should handle different period parameters correctly."""
        # Setup mock data
        mock_diversity_data = {
            "periods": ["2025-01-01"],
            "shannon": [2.3],
            "simpson": [0.8],
            "richness": [15],
            "evenness": [0.7],
        }

        # Configure mocks
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 7),
        )
        client.mock_presentation_manager._get_resolution_for_period.return_value = "hour"
        client.mock_analytics_manager.calculate_diversity_timeline = AsyncMock(
            return_value=mock_diversity_data
        )
        client.mock_presentation_manager._format_diversity_timeline.return_value = (
            mock_diversity_data
        )

        # Test different periods
        for period in ["24h", "7d", "30d", "90d", "365d"]:
            response = client.get(f"/api/analysis/diversity?period={period}")
            assert response.status_code == 200
            data = response.json()
            assert "diversity" in data

    def test_concurrent_requests(self, client):
        """Should handle concurrent requests to different endpoints."""
        import concurrent.futures

        # Setup mock data
        mock_data = {"mock": "data"}

        # Setup temporal patterns mock data with correct structure
        mock_temporal = {
            "hourly_distribution": [0] * 24,
            "peak_hour": 6,
            "periods": ["dawn", "morning", "afternoon", "evening", "night"],
        }

        # Configure all mocks to return quickly
        client.mock_presentation_manager._calculate_analysis_period_dates.return_value = (
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
        )
        client.mock_presentation_manager._get_resolution_for_period.return_value = "day"
        client.mock_presentation_manager._get_window_size_for_period.return_value = 7
        client.mock_presentation_manager._get_days_for_period.return_value = 30
        client.mock_presentation_manager._generate_similarity_periods.return_value = []

        # Configure all async mocks
        client.mock_analytics_manager.calculate_diversity_timeline = AsyncMock(
            return_value=mock_data
        )
        client.mock_analytics_manager.calculate_species_accumulation = AsyncMock(
            return_value=mock_data
        )
        client.mock_analytics_manager.calculate_community_similarity = AsyncMock(
            return_value=mock_data
        )
        client.mock_analytics_manager.calculate_beta_diversity = AsyncMock(return_value=mock_data)
        client.mock_analytics_manager.get_weather_correlation_data = AsyncMock(
            return_value=mock_data
        )
        client.mock_analytics_manager.get_temporal_patterns = AsyncMock(return_value=mock_temporal)
        client.mock_analytics_manager.get_aggregate_hourly_pattern = AsyncMock(
            return_value=[[0] * 24 for _ in range(7)]
        )

        # Configure formatters
        for formatter in [
            "_format_diversity_timeline",
            "_format_accumulation_curve",
            "_format_similarity_matrix",
            "_format_beta_diversity",
            "_format_weather_correlations",
        ]:
            setattr(client.mock_presentation_manager, formatter, MagicMock(return_value=mock_data))

        # Define endpoints to test
        endpoints = [
            "/api/analysis/diversity",
            "/api/analysis/accumulation",
            "/api/analysis/similarity",
            "/api/analysis/beta",
            "/api/analysis/weather",
            "/api/analysis/patterns",
        ]

        # Execute requests concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [
                executor.submit(client.get, f"{endpoint}?period=30d") for endpoint in endpoints
            ]

            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # Verify all requests succeeded
        assert len(results) == 6
        for response in results:
            assert response.status_code == 200
