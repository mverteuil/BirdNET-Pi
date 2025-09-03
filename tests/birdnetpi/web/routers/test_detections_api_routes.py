"""Tests for detections API routes that handle detection CRUD operations and spectrograms."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.manager import DataManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import router


@pytest.fixture
def client():
    """Create test client with detections API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override services with mocks
    mock_data_manager = MagicMock(spec=DataManager)
    # PlottingManager has been removed from the codebase

    # Add query_service attribute to the mock data manager
    mock_data_manager.query_service = None

    container.data_manager.override(mock_data_manager)
    # container.plotting_manager.override() - removed as PlottingManager no longer exists

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.container = container  # type: ignore[attr-defined]

    # Include the router
    app.include_router(router, prefix="/api/detections")

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_data_manager = mock_data_manager  # type: ignore[attr-defined]
    # client.mock_plotting_manager removed - PlottingManager no longer exists

    return client


class TestDetectionsAPIRoutes:
    """Test detections API endpoints."""

    def test_create_detection(self, client):
        """Should create detection successfully."""
        mock_detection = MagicMock()
        mock_detection.id = 123
        client.mock_data_manager.create_detection = AsyncMock(return_value=mock_detection)

        import base64

        test_audio = base64.b64encode(b"test audio data").decode("utf-8")

        detection_data = {
            "species_tensor": "Testus species_Test Bird",
            "scientific_name": "Testus species",
            "common_name": "Test Bird",
            "confidence": 0.95,
            "timestamp": "2025-01-15T10:30:00",
            "audio_data": test_audio,  # Base64-encoded audio
            "sample_rate": 48000,
            "channels": 1,
            "latitude": 63.4591,
            "longitude": -19.3647,
            "species_confidence_threshold": 0.0,
            "week": 3,
            "sensitivity_setting": 1.0,
            "overlap": 0.0,
        }

        response = client.post("/api/detections/", json=detection_data)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Detection received and dispatched"
        assert data["detection_id"] == 123

    def test_get_recent_detections(self, client):
        """Should return recent detections."""
        mock_detections = [
            MagicMock(
                id=1,
                scientific_name="Turdus migratorius",
                common_name="Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30),
                latitude=40.0,
                longitude=-74.0,
            ),
            MagicMock(
                id=2,
                scientific_name="Passer domesticus",
                common_name="Sparrow",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0),
                latitude=40.1,
                longitude=-74.1,
            ),
        ]
        # Mock query_detections instead of get_recent_detections
        client.mock_data_manager.query_detections = AsyncMock(return_value=mock_detections)

        response = client.get("/api/detections/recent?limit=10&include_l10n=false")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["detections"]) == 2
        assert data["detections"][0]["common_name"] == "Robin"

    def test_get_detection_count(self, client):
        """Should return detection count for date."""
        from datetime import UTC, datetime

        today = datetime.now(UTC).date()
        client.mock_data_manager.count_by_date = AsyncMock(return_value={today: 5})

        response = client.get("/api/detections/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5

    def test_get_detection_by_id(self, client):
        """Should return specific detection."""
        mock_detection = MagicMock(
            id=123,
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30),
            latitude=40.0,
            longitude=-74.0,
            species_confidence_threshold=0.0,
            week=3,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)

        response = client.get("/api/detections/123?include_l10n=false")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "123"  # API returns ID as string
        assert data["common_name"] == "Test Bird"

    def test_get_detection_by_id_not_found(self, client):
        """Should return 404 for non-existent detection."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        response = client.get("/api/detections/999?include_l10n=false")

        assert response.status_code == 404

    def test_update_detection_location(self, client):
        """Should update detection location."""
        mock_detection = MagicMock(id=123)
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)
        updated_detection = MagicMock(id=123, latitude=40.1, longitude=-74.1)
        client.mock_data_manager.update_detection = AsyncMock(return_value=updated_detection)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post("/api/detections/123/location", json=location_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Location updated successfully"
        assert data["detection_id"] == 123

    # Spectrogram tests removed - endpoint and PlottingManager have been removed from codebase
