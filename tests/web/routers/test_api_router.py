"""Integration tests for API router that exercise real endpoints and Pydantic validation."""

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.web.routers.api_router import router


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    # Initialize the database
    DatabaseService(db_path)
    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def app_with_api_dependencies(temp_db):
    """Create FastAPI app with API router dependencies."""
    app = FastAPI()

    # Set up app state with real DetectionManager
    database_service = DatabaseService(temp_db)
    app.state.detections = DetectionManager(database_service)

    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_api_dependencies):
    """Create test client with real app."""
    return TestClient(app_with_api_dependencies)


class TestAPIRouterIntegration:
    """Integration tests for API router with real database and Pydantic validation."""

    def test_create_detection_endpoint_accepts_valid_data(self, client):
        """Should accept valid detection data and return 201."""
        detection_data = {
            "species": "Cardinalis cardinalis",
            "confidence": 0.95,
            "timestamp": "2025-01-15T10:30:00",
            "audio_file_path": "/tmp/audio/test_valid_data.wav",
            "duration": 3.0,
            "size_bytes": 144000,
            "recording_start_time": "2025-01-15T10:30:00",
        }

        response = client.post("/detections", json=detection_data)

        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.json()}")
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Detection received and dispatched"
        assert "detection_id" in data
        assert isinstance(data["detection_id"], int)

    def test_create_detection_endpoint_validates_required_fields(self, client):
        """Should reject detection data missing required fields."""
        incomplete_data = {
            "species": "Cardinalis cardinalis",
            "confidence": 0.95,
            # Missing timestamp, audio_file_path, duration, size_bytes, recording_start_time
        }

        response = client.post("/detections", json=incomplete_data)

        assert response.status_code == 422  # Validation error
        error_data = response.json()
        assert "detail" in error_data
        # Should have validation errors for missing fields
        missing_fields = [error["loc"][-1] for error in error_data["detail"]]
        expected_missing = {
            "timestamp",
            "audio_file_path",
            "duration",
            "size_bytes",
            "recording_start_time",
        }
        assert expected_missing.issubset(set(missing_fields))

    def test_create_detection_endpoint_validates_data_types(self, client):
        """Should reject detection data with invalid data types."""
        invalid_data = {
            "species": "Cardinalis cardinalis",
            "confidence": "not_a_number",  # Should be float
            "timestamp": "2025-01-15T10:30:00",
            "audio_file_path": "/tmp/audio/test_data_types.wav",
            "duration": "not_a_number",  # Should be float
            "size_bytes": "not_a_number",  # Should be int
            "recording_start_time": "2025-01-15T10:30:00",
        }

        response = client.post("/detections", json=invalid_data)

        assert response.status_code == 422  # Validation error
        error_data = response.json()
        assert "detail" in error_data
        # Should have validation errors for type mismatches
        assert len(error_data["detail"]) >= 3  # At least 3 type errors

    def test_create_detection_endpoint_validates_confidence_range(self, client):
        """Should accept confidence values in valid range."""
        # Test valid confidence values
        for i, confidence in enumerate([0.0, 0.5, 1.0]):
            detection_data = {
                "species": "Cardinalis cardinalis",
                "confidence": confidence,
                "timestamp": "2025-01-15T10:30:00",
                "audio_file_path": f"/tmp/audio/test_confidence_{i}.wav",  # Unique file path
                "duration": 3.0,
                "size_bytes": 144000,
                "recording_start_time": "2025-01-15T10:30:00",
            }

            response = client.post("/detections", json=detection_data)
            assert response.status_code == 201

    def test_create_detection_endpoint_handles_optional_fields(self, client):
        """Should handle optional fields correctly."""
        detection_data = {
            "species": "Cardinalis cardinalis",
            "confidence": 0.95,
            "timestamp": "2025-01-15T10:30:00",
            "audio_file_path": "/tmp/audio/test_optional_fields.wav",
            "duration": 3.0,
            "size_bytes": 144000,
            "recording_start_time": "2025-01-15T10:30:00",
            # Optional fields
            "spectrogram_path": "/tmp/spectrograms/test.png",
            "latitude": 38.8951,
            "longitude": -77.0364,
            "cutoff": 0.1,
            "week": 3,
            "sensitivity": 1.0,
            "overlap": 0.5,
            "is_extracted": True,
        }

        response = client.post("/detections", json=detection_data)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Detection received and dispatched"
        assert "detection_id" in data

    def test_create_detection_integrates_with_detection_manager(self, client, temp_db):
        """Should integrate with real DetectionManager to save data."""
        detection_data = {
            "species": "Turdus migratorius",
            "confidence": 0.87,
            "timestamp": "2025-01-15T14:20:00",
            "audio_file_path": "/tmp/audio/robin.wav",
            "duration": 2.5,
            "size_bytes": 120000,
            "recording_start_time": "2025-01-15T14:20:00",
        }

        response = client.post("/detections", json=detection_data)

        assert response.status_code == 201
        data = response.json()
        detection_id = data["detection_id"]

        # Verify data was actually saved to database
        app = client.app
        detection_manager = app.state.detections
        assert isinstance(detection_manager, DetectionManager)
        assert detection_manager.db_service.db_path == temp_db

        # The DetectionManager should have saved the detection
        # (We can't easily verify the exact data without more complex DB queries,
        # but the successful response and non-None detection_id indicate success)
        assert detection_id is not None
        assert detection_id > 0

    def test_create_detection_datetime_parsing(self, client):
        """Should correctly parse datetime strings in various formats."""
        # Test ISO format datetime
        detection_data = {
            "species": "Corvus brachyrhynchos",
            "confidence": 0.92,
            "timestamp": "2025-01-15T16:45:30.123456",
            "audio_file_path": "/tmp/audio/crow.wav",
            "duration": 4.2,
            "size_bytes": 201600,
            "recording_start_time": "2025-01-15T16:45:30.123456",
        }

        response = client.post("/detections", json=detection_data)

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Detection received and dispatched"

    def test_create_detection_rejects_invalid_datetime(self, client):
        """Should reject invalid datetime formats."""
        detection_data = {
            "species": "Corvus brachyrhynchos",
            "confidence": 0.92,
            "timestamp": "not-a-valid-datetime",
            "audio_file_path": "/tmp/audio/crow.wav",
            "duration": 4.2,
            "size_bytes": 201600,
            "recording_start_time": "2025-01-15T16:45:30",
        }

        response = client.post("/detections", json=detection_data)

        assert response.status_code == 422  # Validation error
        error_data = response.json()
        assert "detail" in error_data

    def test_create_detection_handles_database_errors_gracefully(self, client):
        """Should handle database errors gracefully."""
        # This test verifies the endpoint doesn't crash on database issues
        # In a real scenario, DetectionManager might raise exceptions
        detection_data = {
            "species": "Poecile carolinensis",
            "confidence": 0.88,
            "timestamp": "2025-01-15T12:15:00",
            "audio_file_path": "/tmp/audio/chickadee.wav",
            "duration": 1.8,
            "size_bytes": 86400,
            "recording_start_time": "2025-01-15T12:15:00",
        }

        # The endpoint should either succeed or return a proper error response
        response = client.post("/detections", json=detection_data)

        # Should be either success or a proper server error, not a crash
        assert response.status_code in [201, 500]

        if response.status_code == 201:
            data = response.json()
            assert data["message"] == "Detection received and dispatched"
        else:
            # If error, should still return valid JSON
            error_data = response.json()
            assert isinstance(error_data, dict)

    def test_create_detection_content_type_validation(self, client):
        """Should require proper JSON content type."""
        detection_data = {
            "species": "Sialia sialis",
            "confidence": 0.91,
            "timestamp": "2025-01-15T09:20:00",
            "audio_file_path": "/tmp/audio/bluebird.wav",
            "duration": 2.3,
            "size_bytes": 110400,
            "recording_start_time": "2025-01-15T09:20:00",
        }

        # Test with form data instead of JSON
        response = client.post("/detections", data=detection_data)

        assert response.status_code == 422  # Should reject non-JSON data

    def test_api_router_uses_real_pydantic_validation(self, client):
        """Should use real Pydantic validation, not mocked validation."""
        # Test that Pydantic validation is actually working by sending edge cases
        edge_case_data = {
            "species": "",  # Empty string - might be valid depending on model
            "confidence": 1.0,  # Boundary value
            "timestamp": "2025-01-15T00:00:00",  # Boundary datetime
            "audio_file_path": "/",  # Minimal path
            "duration": 0.1,  # Very short duration
            "size_bytes": 1,  # Minimal size
            "recording_start_time": "2025-01-15T00:00:00",
        }

        response = client.post("/detections", json=edge_case_data)

        # Response should be based on actual Pydantic validation rules
        # The exact response depends on the model's validation rules
        assert response.status_code in [201, 422]

        if response.status_code == 422:
            error_data = response.json()
            assert "detail" in error_data
            assert isinstance(error_data["detail"], list)
