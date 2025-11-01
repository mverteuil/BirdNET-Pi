"""Tests for SSE (Server-Sent Events) endpoints in detections API routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import router


@pytest.fixture
def sse_client(path_resolver, test_config):
    """Create test client with SSE endpoints and mocked dependencies."""
    app = FastAPI()
    container = Container()
    # IMPORTANT: Override path_resolver BEFORE any other providers to prevent permission errors
    container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))
    mock_detection_query_service = MagicMock(spec=DetectionQueryService)
    container.detection_query_service.override(mock_detection_query_service)
    container.config.override(test_config)
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    client.mock_detection_query_service = mock_detection_query_service  # type: ignore[attr-defined]
    return client


class TestSSEStreaming:
    """Test Server-Sent Events streaming endpoint.

    Note: TestClient doesn't support streaming responses well, so we test
    the event generator logic directly.
    """

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
