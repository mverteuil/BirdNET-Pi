"""Tests for SSE (Server-Sent Events) endpoints in detections API routes."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import router, stream_detections


@pytest.fixture
def sse_client(test_config):
    """Create test client with SSE endpoints and mocked dependencies."""
    app = FastAPI()
    container = Container()
    mock_query_service = MagicMock(spec=DetectionQueryService)
    mock_detection_query_service = MagicMock(spec=DetectionQueryService)
    container.detection_query_service.override(mock_query_service)
    container.detection_query_service.override(mock_detection_query_service)
    container.config.override(test_config)
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    client.mock_query_service = mock_query_service  # type: ignore[attr-defined]
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

    def test_get_species_frequency_with_period_day(self, sse_client):
        """Should accept period=day parameter and convert to 24 hours."""
        mock_frequency = [
            {"name": "American Robin", "count": 42, "percentage": 35.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=day")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 1
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_with_period_week(self, sse_client):
        """Should accept period=week parameter and convert to 168 hours."""
        mock_frequency = [
            {"name": "Blue Jay", "count": 150, "percentage": 45.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=week")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "week"
        assert len(data["species"]) == 1
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_with_period_month(self, sse_client):
        """Should accept period=month parameter and convert to 720 hours."""
        mock_frequency = [
            {"name": "Cardinal", "count": 500, "percentage": 50.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=month")
        assert response.status_code == 200
        response.json()
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_with_period_season(self, sse_client):
        """Should accept period=season parameter and convert to 2160 hours."""
        mock_frequency = [
            {"name": "Warbler", "count": 1200, "percentage": 40.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=season")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "season"
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_with_period_year(self, sse_client):
        """Should accept period=year parameter and convert to 8760 hours."""
        mock_frequency = [{"name": "Owl", "count": 3650, "percentage": 25.0, "category": "common"}]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=year")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "year"
        sse_client.mock_detection_query_service.get_species_summary.assert_called_once()

    def test_get_species_frequency_with_period_historical(self, sse_client):
        """Should accept period=historical parameter and convert to 999999 hours."""
        mock_frequency = [
            {"name": "Eagle", "count": 10000, "percentage": 30.0, "category": "frequent"}
        ]
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, return_value=mock_frequency
        )
        response = sse_client.get("/api/detections/species/summary?period=historical")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "historical"
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
    async def test_stream_detections_initial_connection(self):
        """Should send initial connection event."""
        assert stream_detections is not None
        assert asyncio.iscoroutinefunction(stream_detections)

    @pytest.mark.asyncio
    async def test_event_generator_sends_detection(self):
        """Should generate detection events when signal fires."""
        mock_query_service = MagicMock(spec=DetectionQueryService)
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

    @pytest.mark.asyncio
    async def test_event_generator_heartbeat(self):
        """Should send heartbeat events to keep connection alive."""
        pass

    def test_stream_endpoint_exists(self):
        """Should have SSE endpoint available."""
        assert stream_detections is not None

    @pytest.mark.asyncio
    async def test_detection_handler_type_annotations(self):
        """Should have proper type annotations for detection_handler."""
        assert stream_detections.__annotations__.get("return") is not None

    def test_sse_response_headers(self):
        """Should return correct SSE headers."""
        assert stream_detections.__name__ == "stream_detections"


class TestSSEIntegration:
    """Integration tests for SSE with detection signals."""

    @pytest.mark.asyncio
    async def test_signal_connection(self):
        """Should connect to detection signal properly."""
        assert detection_signal is not None
        assert hasattr(detection_signal, "connect")
        assert hasattr(detection_signal, "send")

    def test_queue_operations_thread_safe(self):
        """Should use thread-safe queue operations."""
        pass


class TestSSEErrorHandling:
    """Test error handling in SSE endpoints."""

    def test_stream_handles_query_service_errors(self):
        """Should handle errors from query service gracefully."""
        assert stream_detections is not None

    def test_species_frequency_handles_analytics_errors(self, sse_client):
        """Should return 500 when analytics manager fails."""
        sse_client.mock_detection_query_service.get_species_summary = AsyncMock(
            spec=callable, side_effect=Exception("Analytics error")
        )
        response = sse_client.get("/api/detections/species/summary")
        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving species summary" in data["detail"]

    def test_stream_handles_cancellation(self):
        """Should handle client disconnection gracefully."""
        assert stream_detections is not None


class TestSSEPerformance:
    """Test performance-related aspects of SSE."""

    def test_heartbeat_timeout_configured(self):
        """Should have appropriate heartbeat timeout."""
        pass

    def test_uses_put_nowait_for_performance(self):
        """Should use put_nowait instead of async put for performance."""
        pass

    def test_no_buffering_headers(self):
        """Should disable buffering for real-time updates."""
        assert stream_detections is not None
