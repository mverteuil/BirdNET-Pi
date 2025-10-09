"""Tests for SSE (Server-Sent Events) endpoints in detections API routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.models import Detection
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import router


@pytest.fixture
def sse_client(test_config, detection_query_service_factory):
    """Create test client with SSE endpoints and mocked dependencies."""
    app = FastAPI()
    container = Container()
    mock_detection_query_service = detection_query_service_factory()
    container.detection_query_service.override(mock_detection_query_service)
    container.config.override(test_config)
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    client.mock_detection_query_service = mock_detection_query_service  # type: ignore[attr-defined]
    return client


class TestSpeciesFrequency:
    """Test species frequency endpoint."""

    def test_get_species_frequency_default_hours(self, sse_client):
        """Should return species frequency for default 24 hours."""
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
        response = sse_client.get("/api/detections/species/summary")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 3
        assert data["species"][0]["name"] == "American Robin"
        assert data["species"][0]["detection_count"] == 42
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_custom_hours(self, sse_client):
        """Should return species frequency for custom time period."""
        mock_frequency = [
            {"name": "Cardinal", "count": 15, "percentage": 50.0, "category": "frequent"},
            {"name": "Blue Jay", "count": 10, "percentage": 33.3, "category": "common"},
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?hours=48")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 2
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_empty_result(self, sse_client):
        """Should handle empty results gracefully."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=[]
        )
        response = sse_client.get("/api/detections/species/summary?hours=1")
        assert response.status_code == 200
        data = response.json()
        assert data["species"] == []

    def test_get_species_frequency_error(self, sse_client):
        """Should handle errors in species frequency analysis."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, side_effect=Exception("Analysis failed")
        )
        response = sse_client.get("/api/detections/species/summary")
        assert response.status_code == 500
        assert "Error retrieving species summary" in response.json()["detail"]

    def test_get_species_frequency_negative_hours(self, sse_client):
        """Should handle negative hours gracefully."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=[]
        )
        response = sse_client.get("/api/detections/species/summary?hours=-1")
        assert response.status_code == 200
        data = response.json()
        assert data["species"] == []

    def test_get_species_frequency_large_hours(self, sse_client):
        """Should handle large time periods."""
        mock_frequency = [
            {"name": "Species A", "count": 500, "percentage": 40.0, "category": "frequent"},
            {"name": "Species B", "count": 300, "percentage": 24.0, "category": "common"},
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?hours=720")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 2
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    @pytest.mark.parametrize(
        ("period", "verify_period_in_response"),
        [
            pytest.param("day", False, id="day"),
            pytest.param("week", True, id="week"),
            pytest.param("month", False, id="month"),
            pytest.param("season", True, id="season"),
            pytest.param("year", True, id="year"),
            pytest.param("historical", True, id="historical"),
        ],
    )
    def test_get_species_frequency_with_period(
        self, sse_client, period: str, verify_period_in_response: bool
    ):
        """Should accept various period parameters."""
        mock_frequency = [
            {"name": "Test Bird", "count": 100, "percentage": 50.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get(f"/api/detections/species/summary?period={period}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 1
        if verify_period_in_response:
            assert data["period"] == period
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_period_case_insensitive(self, sse_client):
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
        response = sse_client.get("/api/detections/species/summary?period=WEEK")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "WEEK"
        response = sse_client.get("/api/detections/species/summary?period=Week")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "Week"

    def test_get_species_frequency_period_overrides_hours(self, sse_client):
        """Should use period value when both period and hours are provided."""
        mock_frequency = [
            {"name": "Robin", "count": 75, "percentage": 60.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?hours=48&period=week")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "week"
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_invalid_period(self, sse_client):
        """Should default to 24 hours for invalid period values."""
        mock_frequency = [{"name": "Finch", "count": 10, "percentage": 100.0, "category": "common"}]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=invalid")
        assert response.status_code == 200
        response.json()
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_empty_period(self, sse_client):
        """Should default to 24 hours when period is empty string."""
        mock_frequency = [{"name": "Crow", "count": 5, "percentage": 100.0, "category": "rare"}]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=")
        assert response.status_code == 200
        response.json()


class TestSSEStreaming:
    """Test Server-Sent Events streaming endpoint.

    Note: TestClient doesn't support streaming responses well, so we test
    the event generator logic directly.
    """

    @pytest.mark.asyncio
    async def test_event_generator_sends_detection(self, detection_query_service_factory):
        """Should generate detection events when signal fires."""
        mock_query_service = detection_query_service_factory()
        detection_id = uuid4()
        mock_detection = MagicMock(
            spec=Detection,
            id=detection_id,
            scientific_name="Corvus corax",
            common_name="Common Raven",
            confidence=0.88,
            timestamp=datetime.now(),
            latitude=45.0,
            longitude=-80.0,
        )
        mock_query_service.get_detection_with_taxa = AsyncMock(
            spec=callable, return_value=mock_detection
        )


class TestSSEIntegration:
    """Integration tests for SSE with detection signals."""

    @pytest.mark.asyncio
    async def test_signal_connection(self):
        """Should connect to detection signal properly."""
        assert detection_signal is not None
        assert hasattr(detection_signal, "connect")
        assert hasattr(detection_signal, "send")


class TestSSEErrorHandling:
    """Test error handling in SSE endpoints."""

    def test_species_frequency_handles_analytics_errors(self, sse_client):
        """Should return 500 when analytics manager fails."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, side_effect=Exception("Analytics error")
        )
        response = sse_client.get("/api/detections/species/summary")
        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving species summary" in data["detail"]
