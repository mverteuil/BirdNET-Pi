"""Test suite for detections router."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.web.main import app


class TestDetectionsRouter:
    """Test class for detection router endpoints."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock DetectionManager
        mock_detection_manager = Mock()
        app.state.detections = mock_detection_manager

        # Add mock config object that templates expect
        app.state.config = BirdNETConfig(site_name="Test BirdNET-Pi")

        self.client = TestClient(app)
        self.mock_detection_manager = mock_detection_manager

    def test_create_detection_endpoint(self):
        """Test POST /api/detections endpoint."""
        # Mock the create_detection method
        mock_detection = Mock()
        mock_detection.id = 123
        self.mock_detection_manager.create_detection.return_value = mock_detection

        detection_data = {
            "species": "Test Bird",
            "confidence": 0.95,
            "timestamp": datetime.now().isoformat(),
            "audio_file_path": "test.wav",
            "duration": 3.0,
            "size_bytes": 1024,
            "recording_start_time": datetime.now().isoformat(),
            "latitude": 40.7128,
            "longitude": -74.0060,
            "cutoff": 0.5,
            "week": 10,
            "sensitivity": 0.8,
            "overlap": 0.1,
            "is_extracted": False,
        }

        response = self.client.post("/api/detections/", json=detection_data)

        assert response.status_code == 201
        response_data = response.json()
        assert response_data["message"] == "Detection received and dispatched"
        assert response_data["detection_id"] == 123
        self.mock_detection_manager.create_detection.assert_called_once()

    def test_get_recent_detections_endpoint(self):
        """Test GET /api/detections/recent endpoint."""
        # Mock recent detections
        mock_detection = Mock()
        mock_detection.id = 1
        mock_detection.species = "Test Bird"
        mock_detection.confidence = 0.95
        mock_detection.timestamp = datetime.now()
        mock_detection.latitude = 40.7128
        mock_detection.longitude = -74.0060

        self.mock_detection_manager.get_recent_detections.return_value = [mock_detection]

        response = self.client.get("/api/detections/recent?limit=5")

        assert response.status_code == 200
        response_data = response.json()
        assert "detections" in response_data
        assert "count" in response_data
        assert response_data["count"] == 1
        self.mock_detection_manager.get_recent_detections.assert_called_once_with(5)

    def test_get_detection_count_endpoint(self):
        """Test GET /api/detections/count endpoint."""
        self.mock_detection_manager.get_detections_count_by_date.return_value = 42

        response = self.client.get("/api/detections/count")

        assert response.status_code == 200
        response_data = response.json()
        assert "date" in response_data
        assert "count" in response_data
        assert response_data["count"] == 42
        self.mock_detection_manager.get_detections_count_by_date.assert_called_once()

    def test_get_detection_count_with_date_endpoint(self):
        """Test GET /api/detections/count with specific date."""
        self.mock_detection_manager.get_detections_count_by_date.return_value = 15

        response = self.client.get("/api/detections/count?target_date=2023-10-15")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["date"] == "2023-10-15"
        assert response_data["count"] == 15

    def test_update_detection_location_endpoint(self):
        """Test POST /api/detections/{id}/location endpoint."""
        # Mock detection
        mock_detection = Mock()
        mock_detection.id = 123
        self.mock_detection_manager.get_detection_by_id.return_value = mock_detection
        self.mock_detection_manager.update_detection_location.return_value = True

        location_data = {"latitude": 40.7128, "longitude": -74.0060}

        response = self.client.post("/api/detections/123/location", json=location_data)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["message"] == "Location updated successfully"
        assert response_data["detection_id"] == 123
        assert response_data["latitude"] == 40.7128
        assert response_data["longitude"] == -74.0060

    def test_update_detection_location_not_found(self):
        """Test POST /api/detections/{id}/location with non-existent detection."""
        self.mock_detection_manager.get_detection_by_id.return_value = None

        location_data = {"latitude": 40.7128, "longitude": -74.0060}

        response = self.client.post("/api/detections/999/location", json=location_data)

        assert response.status_code == 404
        response_data = response.json()
        assert response_data["detail"] == "Detection not found"

    def test_get_detection_by_id_endpoint(self):
        """Test GET /api/detections/{id} endpoint."""
        # Mock detection
        mock_detection = Mock()
        mock_detection.id = 123
        mock_detection.species = "Test Bird"
        mock_detection.confidence = 0.95
        mock_detection.timestamp = datetime.now()
        mock_detection.latitude = 40.7128
        mock_detection.longitude = -74.0060
        mock_detection.cutoff = 0.5
        mock_detection.week = 10
        mock_detection.sensitivity = 0.8
        mock_detection.overlap = 0.1

        self.mock_detection_manager.get_detection_by_id.return_value = mock_detection

        response = self.client.get("/api/detections/123")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == 123
        assert response_data["species"] == "Test Bird"
        assert response_data["confidence"] == 0.95
        self.mock_detection_manager.get_detection_by_id.assert_called_once_with(123)

    def test_get_detection_by_id_not_found(self):
        """Test GET /api/detections/{id} with non-existent detection."""
        self.mock_detection_manager.get_detection_by_id.return_value = None

        response = self.client.get("/api/detections/999")

        assert response.status_code == 404
        response_data = response.json()
        assert response_data["detail"] == "Detection not found"
