"""Tests for detection API routes that handle detection CRUD operations and spectrograms."""

from unittest.mock import MagicMock

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.web.routers.detection_api_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""
    
    detection_manager = providers.Singleton(MagicMock, spec=DetectionManager)
    plotting_manager = providers.Singleton(MagicMock, spec=PlottingManager)


@pytest.fixture
def app_with_detection_router():
    """Create FastAPI app with detection router and DI container."""
    app = FastAPI()
    
    # Setup test container
    container = TestContainer()
    app.container = container
    
    # Wire the router module
    container.wire(modules=["birdnetpi.web.routers.detection_api_routes"])
    
    # Include the router
    app.include_router(router, prefix="/api")
    
    return app


@pytest.fixture
def client(app_with_detection_router):
    """Create test client."""
    return TestClient(app_with_detection_router)


class TestDetectionEndpoints:
    """Test detection-related API endpoints."""

    def test_get_detections_success(self, client):
        """Should return detections with count."""
        mock_detections = [{"id": 1, "species": "Robin"}, {"id": 2, "species": "Sparrow"}]
        client.app.container.detection_manager().get_recent_detections.return_value = mock_detections

        response = client.get("/api/detections?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["detections"] == mock_detections
        assert data["count"] == 2

    def test_get_detections_default_params(self, client):
        """Should use default limit and offset parameters."""
        client.app.container.detection_manager().get_recent_detections.return_value = []

        response = client.get("/api/detections")

        assert response.status_code == 200
        client.app.container.detection_manager().get_recent_detections.assert_called_once_with(limit=100)

    def test_get_detection_spectrogram_success(self, client):
        """Should generate and return spectrogram for detection."""
        mock_spectrogram_buffer = MagicMock()
        mock_spectrogram_buffer.read.return_value = b"fake_png_data"
        client.app.container.plotting_manager().generate_spectrogram.return_value = mock_spectrogram_buffer
        
        response = client.get("/api/detections/123/spectrogram?audio_path=/path/to/audio.wav")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        client.app.container.plotting_manager().generate_spectrogram.assert_called_once_with("/path/to/audio.wav")

    def test_get_detection_spectrogram_missing_audio_path(self, client):
        """Should require audio_path parameter."""
        response = client.get("/api/detections/123/spectrogram")
        
        assert response.status_code == 422  # Validation error

    def test_get_detection_spectrogram_error_handling(self, client):
        """Should handle plotting manager errors."""
        client.app.container.plotting_manager().generate_spectrogram.side_effect = Exception("Plotting error")
        
        response = client.get("/api/detections/123/spectrogram?audio_path=/path/to/audio.wav")
        
        assert response.status_code == 500
        assert "Error generating spectrogram" in response.json()["detail"]