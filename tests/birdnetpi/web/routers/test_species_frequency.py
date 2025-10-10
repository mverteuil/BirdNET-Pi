"""Refactored TestSpeciesFrequency with parameterization."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import router


@pytest.fixture
def sse_client(test_config):
    """Create test client with SSE endpoints and mocked dependencies."""
    app = FastAPI()
    container = Container()
    mock_detection_query_service = MagicMock(spec=DetectionQueryService)
    container.detection_query_service.override(mock_detection_query_service)
    container.config.override(test_config)
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    client.mock_detection_query_service = mock_detection_query_service  # type: ignore[attr-defined]
    return client


class TestSpeciesFrequency:
    """Test species frequency endpoint with parameterized tests."""

    @pytest.mark.parametrize(
        "period,expected_species_count,mock_frequency",
        [
            pytest.param(
                "day",
                1,
                [
                    {
                        "common_name": "American Robin",
                        "scientific_name": "Turdus migratorius",
                        "count": 42,
                        "percentage": 35.0,
                        "category": "frequent",
                    }
                ],
                id="period_day",
            ),
            pytest.param(
                "week",
                1,
                [
                    {
                        "common_name": "Blue Jay",
                        "scientific_name": "Cyanocitta cristata",
                        "count": 150,
                        "percentage": 45.0,
                        "category": "frequent",
                    }
                ],
                id="period_week",
            ),
            pytest.param(
                "month",
                1,
                [
                    {
                        "common_name": "Cardinal",
                        "scientific_name": "Cardinalis cardinalis",
                        "count": 500,
                        "percentage": 50.0,
                        "category": "frequent",
                    }
                ],
                id="period_month",
            ),
            pytest.param(
                "season",
                1,
                [
                    {
                        "common_name": "Warbler",
                        "scientific_name": "Setophaga spp.",
                        "count": 1200,
                        "percentage": 40.0,
                        "category": "frequent",
                    }
                ],
                id="period_season",
            ),
            pytest.param(
                "year",
                1,
                [
                    {
                        "common_name": "Owl",
                        "scientific_name": "Strix varia",
                        "count": 3650,
                        "percentage": 25.0,
                        "category": "common",
                    }
                ],
                id="period_year",
            ),
            pytest.param(
                "historical",
                1,
                [
                    {
                        "common_name": "Eagle",
                        "scientific_name": "Haliaeetus leucocephalus",
                        "count": 10000,
                        "percentage": 30.0,
                        "category": "frequent",
                    }
                ],
                id="period_historical",
            ),
        ],
    )
    def test_get_species_frequency_with_period(
        self, sse_client, period, expected_species_count, mock_frequency
    ):
        """Should accept period parameter and return correct species data."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )

        response = sse_client.get(f"/api/detections/species/summary?period={period}")

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == period
        assert len(data["species"]) == expected_species_count
        assert data["species"][0]["name"] == mock_frequency[0]["common_name"]
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    @pytest.mark.parametrize(
        "hours,expected_count,test_description",
        [
            pytest.param(None, 3, "default 24 hours", id="default_hours"),
            pytest.param(48, 2, "custom 48 hours", id="custom_48h"),
            pytest.param(1, 0, "empty result for 1 hour", id="empty_1h"),
            pytest.param(-1, 0, "negative hours handled gracefully", id="negative_hours"),
            pytest.param(720, 2, "large time period (30 days)", id="large_period"),
        ],
    )
    def test_get_species_frequency_various_hours(
        self, sse_client, hours, expected_count, test_description
    ):
        """Should handle various hour values correctly: {test_description}."""
        # Create appropriate mock data based on expected count
        if expected_count == 0:
            mock_frequency = []
        elif expected_count == 2:
            mock_frequency = [
                {"name": "Species A", "count": 500, "percentage": 40.0, "category": "frequent"},
                {"name": "Species B", "count": 300, "percentage": 24.0, "category": "common"},
            ]
        else:  # expected_count == 3
            mock_frequency = [
                {
                    "common_name": "American Robin",
                    "scientific_name": "Turdus migratorius",
                    "count": 42,
                    "percentage": 35.0,
                    "category": "frequent",
                },
                {
                    "common_name": "House Sparrow",
                    "scientific_name": "Passer domesticus",
                    "count": 30,
                    "percentage": 25.0,
                    "category": "frequent",
                },
                {
                    "common_name": "Blue Jay",
                    "scientific_name": "Cyanocitta cristata",
                    "count": 20,
                    "percentage": 16.7,
                    "category": "common",
                },
            ]

        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )

        # Build URL with optional hours parameter
        url = "/api/detections/species/summary"
        if hours is not None:
            url = f"{url}?hours={hours}"

        response = sse_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == expected_count
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    @pytest.mark.parametrize(
        "period,case_variation",
        [
            pytest.param("week", "WEEK", id="uppercase"),
            pytest.param("week", "Week", id="titlecase"),
            pytest.param("week", "week", id="lowercase"),
        ],
    )
    def test_get_species_frequency_period_case_insensitive(
        self, sse_client, period, case_variation
    ):
        """Should handle period parameter case-insensitively."""
        mock_frequency = [
            {
                "common_name": "Sparrow",
                "scientific_name": "Passer domesticus",
                "count": 20,
                "percentage": 100.0,
                "category": "frequent",
            }
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )

        response = sse_client.get(f"/api/detections/species/summary?period={case_variation}")

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == case_variation
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    @pytest.mark.parametrize(
        "side_effect,expected_status,expected_detail",
        [
            pytest.param(
                Exception("Analysis failed"),
                500,
                "Error retrieving species summary",
                id="analysis_failure",
            ),
            pytest.param(
                Exception("Analytics error"),
                500,
                "Error retrieving species summary",
                id="analytics_error",
            ),
        ],
    )
    def test_get_species_frequency_error_handling(
        self, sse_client, side_effect, expected_status, expected_detail
    ):
        """Should handle errors in species frequency analysis."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, side_effect=side_effect
        )

        response = sse_client.get("/api/detections/species/summary")

        assert response.status_code == expected_status
        assert expected_detail in response.json()["detail"]
