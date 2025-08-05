"""Tests for detections API routes that handle detection CRUD operations and spectrograms."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.web.routers.detections_api_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""

    detection_manager = providers.Singleton(MagicMock, spec=DetectionManager)
    plotting_manager = providers.Singleton(MagicMock, spec=PlottingManager)


@pytest.fixture
def app_with_detections_router():
    """Create FastAPI app with detections router and DI container."""
    app = FastAPI()

    # Setup test container
    container = TestContainer()
    app.container = container

    # Wire the router module
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])

    # Include the router
    app.include_router(router, prefix="/api/detections")

    return app


@pytest.fixture
def client(app_with_detections_router):
    """Create test client."""
    return TestClient(app_with_detections_router)


class TestDetectionsAPIRoutes:
    """Test detections API endpoints."""

    def test_create_detection_success(self, client):
        """Should create detection successfully."""
        mock_detection = MagicMock()
        mock_detection.id = 123
        client.app.container.detection_manager().create_detection.return_value = mock_detection

        detection_data = {
            "species_tensor": "Testus species_Test Bird",
            "scientific_name": "Testus species",
            "common_name_tensor": "Test Bird",
            "confidence": 0.95,
            "timestamp": "2025-01-15T10:30:00",
            "audio_file_path": "/test/audio.wav",
            "duration": 3.0,
            "size_bytes": 1024,
            "recording_start_time": "2025-01-15T10:30:00",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "cutoff": 0.0,
            "week": 3,
            "sensitivity": 1.0,
            "overlap": 0.0
        }

        response = client.post("/api/detections/", json=detection_data)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Detection received and dispatched"
        assert data["detection_id"] == 123

    def test_get_recent_detections_success(self, client):
        """Should return recent detections."""
        mock_detections = [
            MagicMock(
                id=1,
                species="Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30),
                latitude=40.0,
                longitude=-74.0
            ),
            MagicMock(
                id=2,
                species="Sparrow",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0),
                latitude=40.1,
                longitude=-74.1
            )
        ]
        client.app.container.detection_manager().get_recent_detections.return_value = mock_detections

        response = client.get("/api/detections/recent?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["detections"]) == 2
        assert data["detections"][0]["species"] == "Robin"

    def test_get_detection_count_success(self, client):
        """Should return detection count for date."""
        client.app.container.detection_manager().get_detections_count_by_date.return_value = 5

        response = client.get("/api/detections/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5

    def test_get_detection_by_id_success(self, client):
        """Should return specific detection."""
        mock_detection = MagicMock(
            id=123,
            species="Test Bird",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30),
            latitude=40.0,
            longitude=-74.0,
            cutoff=0.0,
            week=3,
            sensitivity=1.0,
            overlap=0.0
        )
        client.app.container.detection_manager().get_detection_by_id.return_value = mock_detection

        response = client.get("/api/detections/123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["species"] == "Test Bird"

    def test_get_detection_by_id_not_found(self, client):
        """Should return 404 for non-existent detection."""
        client.app.container.detection_manager().get_detection_by_id.return_value = None

        response = client.get("/api/detections/999")

        assert response.status_code == 404

    def test_update_detection_location_success(self, client):
        """Should update detection location."""
        mock_detection = MagicMock(id=123)
        client.app.container.detection_manager().get_detection_by_id.return_value = mock_detection
        client.app.container.detection_manager().update_detection_location.return_value = True

        location_data = {
            "latitude": 41.0,
            "longitude": -75.0
        }

        response = client.post("/api/detections/123/location", json=location_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Location updated successfully"
        assert data["detection_id"] == 123

    def test_get_detection_spectrogram_success(self, client):
        """Should generate and return spectrogram for detection."""
        mock_detection = MagicMock()
        mock_detection.audio_file_path = "/path/to/audio.wav"
        client.app.container.detection_manager().get_detection_by_id.return_value = mock_detection

        mock_spectrogram_buffer = MagicMock()
        mock_spectrogram_buffer.read.return_value = b"fake_png_data"
        client.app.container.plotting_manager().generate_spectrogram.return_value = mock_spectrogram_buffer

        response = client.get("/api/detections/123/spectrogram")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        client.app.container.plotting_manager().generate_spectrogram.assert_called_once_with(
            "/path/to/audio.wav"
        )

    def test_get_detection_spectrogram_not_found(self, client):
        """Should return 404 for non-existent detection."""
        client.app.container.detection_manager().get_detection_by_id.return_value = None

        response = client.get("/api/detections/999/spectrogram")

        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]

    def test_get_detection_spectrogram_no_audio_file(self, client):
        """Should return 404 when detection has no audio file."""
        mock_detection = MagicMock()
        mock_detection.audio_file_path = None
        client.app.container.detection_manager().get_detection_by_id.return_value = mock_detection

        response = client.get("/api/detections/123/spectrogram")

        assert response.status_code == 404
        assert "No audio file associated" in response.json()["detail"]

    def test_get_detection_spectrogram_error_handling(self, client):
        """Should handle plotting manager errors."""
        mock_detection = MagicMock()
        mock_detection.audio_file_path = "/path/to/audio.wav"
        client.app.container.detection_manager().get_detection_by_id.return_value = mock_detection

        client.app.container.plotting_manager().generate_spectrogram.side_effect = Exception("Plotting error")

        response = client.get("/api/detections/123/spectrogram")

        assert response.status_code == 500
        assert "Error generating spectrogram" in response.json()["detail"]