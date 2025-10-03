"""Tests for detections API routes that handle detection CRUD operations and spectrograms."""

import asyncio
import base64
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import (
    _create_detection_handler,
    _format_detection_event,
    router,
)


@pytest.fixture
def client(path_resolver, test_config):
    """Create test client with detections API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override services with mocks
    mock_data_manager = MagicMock(spec=DataManager)
    mock_query_service = MagicMock(spec=DetectionQueryService)

    # Add query_service attribute to the mock data manager
    mock_data_manager.query_service = None

    container.data_manager.override(mock_data_manager)
    container.detection_query_service.override(mock_query_service)

    # Use the real test config from the fixture
    container.config.override(test_config)

    # Mock the cache service to avoid Redis connection issues
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_cache.set.return_value = True
    mock_cache.delete.return_value = True
    mock_cache.clear.return_value = True
    mock_cache.ping.return_value = True
    mock_cache.get_stats.return_value = {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "deletes": 0,
        "pattern_deletes": 0,
        "errors": 0,
        "hit_rate": 0.0,
        "total_requests": 0,
        "backend": "mock",
    }
    container.cache_service.override(mock_cache)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])

    # Include the router
    # Router already has prefix="/detections", so we only add "/api"
    app.include_router(router, prefix="/api")

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_data_manager = mock_data_manager  # type: ignore[attr-defined]
    client.mock_query_service = mock_query_service  # type: ignore[attr-defined]
    client.test_config = test_config  # type: ignore[attr-defined]

    return client


class TestDetectionsAPIRoutes:
    """Test detections API endpoints."""

    def test_create_detection(self, client, model_factory):
        """Should create detection successfully."""
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_detection = model_factory.create_detection()
        mock_detection.id = test_uuid
        client.mock_data_manager.create_detection = AsyncMock(return_value=mock_detection)

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
        assert data["detection_id"] == str(test_uuid)

    def test_create_detection_validation_error(self, client):
        """Should handle validation errors when creating detection."""
        # Test with missing required fields
        detection_data = {
            "species_tensor": "Testus species_Test Bird",
            "scientific_name": "Testus species",
            # Missing many required fields
        }

        response = client.post("/api/detections/", json=detection_data)

        # Should get validation error
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_get_recent_detections(self, client, model_factory):
        """Should return recent detections."""
        # Create actual DetectionWithTaxa objects using model_factory
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
                latitude=40.0,
                longitude=-74.0,
                ioc_english_name="American Robin",
                translated_name="Robin",
                family="Turdidae",
                genus="Turdus",
                order_name="Passeriformes",
            ),
            model_factory.create_detection_with_taxa(
                species_tensor="Passer domesticus_House Sparrow",
                scientific_name="Passer domesticus",
                common_name="Sparrow",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=UTC),
                latitude=40.1,
                longitude=-74.1,
                ioc_english_name="House Sparrow",
                translated_name="Sparrow",
                family="Passeridae",
                genus="Passer",
                order_name="Passeriformes",
            ),
        ]
        # Mock query_detections on DetectionQueryService (not DataManager)
        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        response = client.get("/api/detections/recent?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["detections"]) == 2
        assert data["detections"][0]["common_name"] == "Robin"

    def test_get_recent_detections_error(self, client):
        """Should handle errors when getting recent detections."""
        client.mock_query_service.query_detections = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/recent?limit=10")

        assert response.status_code == 500
        assert "Error retrieving recent detections" in response.json()["detail"]

    def test_get_detection_count(self, client):
        """Should return detection count for date."""
        today = datetime.now(UTC).date()
        client.mock_query_service.count_by_date = AsyncMock(return_value={today: 5})

        response = client.get("/api/detections/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5

    def test_get_detection_count_with_specific_date(self, client):
        """Should return detection count for specific date."""
        target_date = date(2025, 1, 15)
        client.mock_query_service.count_by_date = AsyncMock(return_value={target_date: 42})

        response = client.get(f"/api/detections/count?target_date={target_date.isoformat()}")

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2025-01-15"
        assert data["count"] == 42

    def test_get_detection_count_zero_detections(self, client):
        """Should return zero when no detections exist for date."""
        empty_date = date(2020, 1, 1)
        client.mock_query_service.count_by_date = AsyncMock(return_value={})

        response = client.get(f"/api/detections/count?target_date={empty_date.isoformat()}")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    def test_get_detection_by_id(self, client, model_factory):
        """Should return specific detection."""
        mock_detection = model_factory.create_detection(
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
            latitude=40.0,
            longitude=-74.0,
            species_confidence_threshold=0.0,
            week=3,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        # Mock the correct method on the correct service
        client.mock_query_service.get_detection_with_taxa = AsyncMock(return_value=mock_detection)

        # Use the detection's actual UUID
        response = client.get(f"/api/detections/{mock_detection.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"]  # ID should be present as a UUID string
        assert data["common_name"] == "Test Bird"

    def test_get_detection_by_id_not_found(self, client):
        """Should return 404 for non-existent detection."""
        # Mock the correct method on the correct service
        client.mock_query_service.get_detection_with_taxa = AsyncMock(return_value=None)

        # Use a valid UUID that doesn't exist
        response = client.get(f"/api/detections/{uuid4()}")

        assert response.status_code == 404

    def test_update_detection_location(self, client, model_factory):
        """Should update detection location."""
        mock_detection = model_factory.create_detection()
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)
        updated_detection = model_factory.create_detection(
            id=mock_detection.id, latitude=40.1, longitude=-74.1
        )
        client.mock_data_manager.update_detection = AsyncMock(return_value=updated_detection)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post(f"/api/detections/{mock_detection.id}/location", json=location_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Location updated successfully"
        assert data["detection_id"] == str(mock_detection.id)

    def test_update_detection_location_not_found(self, client):
        """Should return 404 when updating location of non-existent detection."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post(f"/api/detections/{uuid4()}/location", json=location_data)

        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]

    def test_update_detection_location_failed(self, client, model_factory):
        """Should handle update failure."""
        mock_detection = model_factory.create_detection()
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)
        client.mock_data_manager.update_detection = AsyncMock(return_value=None)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post(f"/api/detections/{mock_detection.id}/location", json=location_data)

        assert response.status_code == 500
        assert "Failed to update detection location" in response.json()["detail"]

    def test_update_detection_location_error(self, client):
        """Should handle unexpected errors in location update."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(
            side_effect=Exception("Database error")
        )

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post(f"/api/detections/{uuid4()}/location", json=location_data)

        assert response.status_code == 500
        assert "Error updating detection location" in response.json()["detail"]


class TestPaginatedDetections:
    """Test paginated detections endpoint."""

    def test_get_paginated_detections(self, client, model_factory):
        """Should return paginated detections."""
        # Mock DetectionWithTaxa objects
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor=f"Species {i}_Common {i}",
                scientific_name=f"Species {i}",
                common_name=f"Common {i}",
                confidence=0.9,
                timestamp=datetime(2025, 1, 15, 10, i % 60, tzinfo=UTC),
                latitude=40.0,
                longitude=-74.0,
                ioc_english_name=f"IOC Name {i}",
                translated_name=f"Translated {i}",
                family=f"Family {i % 3}",
                genus=f"Genus {i % 2}",
                order_name="Passeriformes",
            )
            for i in range(25)  # Create 25 detections for pagination testing
        ]

        # Mock query_detections on DetectionQueryService
        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        response = client.get("/api/detections/?page=1&per_page=10&period=week")

        assert response.status_code == 200
        data = response.json()
        assert len(data["detections"]) == 10
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["per_page"] == 10
        assert data["pagination"]["total"] == 25
        assert data["pagination"]["total_pages"] == 3
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is False

    def test_get_paginated_detections_with_search(self, client, model_factory):
        """Should filter paginated detections by search term."""
        # Mock detections with different names
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
            ),
            model_factory.create_detection_with_taxa(
                species_tensor="Corvus corax_Common Raven",
                scientific_name="Corvus corax",
                common_name="Common Raven",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=UTC),
            ),
            model_factory.create_detection_with_taxa(
                species_tensor="Passer domesticus_House Sparrow",
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                confidence=0.92,
                timestamp=datetime(2025, 1, 15, 11, 30, tzinfo=UTC),
            ),
        ]

        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        # Search for "Robin"
        response = client.get("/api/detections/?search=Robin")

        assert response.status_code == 200
        data = response.json()
        assert len(data["detections"]) == 1
        assert data["detections"][0]["common_name"] == "American Robin"

    def test_get_paginated_detections_empty_result(self, client):
        """Should handle empty results gracefully."""
        client.mock_query_service.query_detections = AsyncMock(return_value=[])

        response = client.get("/api/detections/?page=1")

        assert response.status_code == 200
        data = response.json()
        assert data["detections"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["total_pages"] == 0

    def test_get_paginated_detections_error(self, client):
        """Should handle errors in paginated detections."""
        client.mock_query_service.query_detections = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/?page=1&per_page=10")

        assert response.status_code == 500
        assert "Error retrieving detections" in response.json()["detail"]

    def test_get_paginated_detections_default_dates(self, client, model_factory):
        """Should use today's date when start_date and end_date not provided."""
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor="Today Species_Today Bird",
                scientific_name="Today Species",
                common_name="Today Bird",
                confidence=0.88,
                timestamp=datetime.now(UTC),
            )
        ]

        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        # Don't provide dates - should default to today
        response = client.get("/api/detections/?page=1&per_page=20")

        assert response.status_code == 200
        # Should use default dates (tested by successful response)
        data = response.json()
        assert "detections" in data
        assert "pagination" in data


class TestBestRecordings:
    """Test best recordings endpoint."""

    def test_get_best_recordings(self, client, model_factory):
        """Should return best recordings with highest confidence."""
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                ioc_english_name="American Robin",
                confidence=0.98,
                timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
                family="Turdidae",
                genus="Turdus",
            ),
            model_factory.create_detection_with_taxa(
                species_tensor="Corvus corax_Common Raven",
                scientific_name="Corvus corax",
                common_name="Common Raven",
                ioc_english_name="Common Raven",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=UTC),
                family="Corvidae",
                genus="Corvus",
            ),
        ]

        # Mock the query_best_recordings_per_species method to return (detections, total_count)
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            return_value=(mock_detections, len(mock_detections))
        )

        response = client.get(
            "/api/detections/best-recordings?min_confidence=0.9&page=1&per_page=50"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 2
        assert data["recordings"][0]["confidence"] == 0.98  # Confidence is 0-1, not percentage
        assert data["count"] == 2
        assert data["unique_species"] == 2
        assert data["avg_confidence"] > 0
        # Check pagination metadata
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["total"] == 2
        # Check that taxonomy fields are present
        assert data["recordings"][0]["family"] == "Turdidae"
        assert data["recordings"][0]["genus"] == "Turdus"
        assert data["recordings"][1]["family"] == "Corvidae"
        assert data["recordings"][1]["genus"] == "Corvus"

    def test_get_best_recordings_with_family_filter(self, client, model_factory):
        """Should filter best recordings by family."""
        mock_detections = [
            model_factory.create_detection_with_taxa(
                species_tensor="Corvus corax_Common Raven",
                scientific_name="Corvus corax",
                common_name="Common Raven",
                ioc_english_name="Common Raven",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
                family="Corvidae",
                genus="Corvus",
            ),
        ]

        # Mock the query_best_recordings_per_species method to return (detections, total_count)
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            return_value=(mock_detections, 1)
        )

        response = client.get("/api/detections/best-recordings?family=Corvidae")

        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 1
        assert data["recordings"][0]["family"] == "Corvidae"
        assert data["filters"]["family"] == "Corvidae"

    def test_get_best_recordings_empty(self, client):
        """Should handle empty results for best recordings."""
        # Mock the query_best_recordings_per_species method to return empty results
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            return_value=([], 0)
        )

        response = client.get("/api/detections/best-recordings?min_confidence=0.99")

        assert response.status_code == 200
        data = response.json()
        assert data["recordings"] == []
        assert data["count"] == 0
        assert data["avg_confidence"] == 0
        assert data["date_range"] == "No recordings"

    def test_get_best_recordings_error(self, client):
        """Should handle errors in best recordings."""
        # Mock the query_best_recordings_per_species method to raise an error
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            side_effect=Exception("Query failed")
        )

        response = client.get("/api/detections/best-recordings")

        assert response.status_code == 500
        assert "Error retrieving best recordings" in response.json()["detail"]

    def test_get_best_recordings_with_species_filter_no_limit(self, client, model_factory):
        """Should pass None per_species_limit when species filter is provided."""
        mock_detection = model_factory.create_detection_with_taxa(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
        )

        # Mock the query_best_recordings_per_species method
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            return_value=([mock_detection], 1)
        )

        # Request with species filter
        response = client.get("/api/detections/best-recordings?species=Turdus%20migratorius")

        assert response.status_code == 200

        # Verify that per_species_limit was set to None for species filter
        client.mock_query_service.query_best_recordings_per_species.assert_called_once()
        call_args = client.mock_query_service.query_best_recordings_per_species.call_args
        assert call_args.kwargs["per_species_limit"] is None
        assert call_args.kwargs["species"] == "Turdus migratorius"

    def test_get_best_recordings_without_species_uses_default_limit(self, client, model_factory):
        """Should use default per_species_limit when no species filter."""
        mock_detection = model_factory.create_detection_with_taxa(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
        )

        # Mock the query_best_recordings_per_species method
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            return_value=([mock_detection], 1)
        )

        # Request without species filter
        response = client.get("/api/detections/best-recordings")

        assert response.status_code == 200

        # Verify that per_species_limit was set to 5 (default)
        client.mock_query_service.query_best_recordings_per_species.assert_called_once()
        call_args = client.mock_query_service.query_best_recordings_per_species.call_args
        assert call_args.kwargs["per_species_limit"] == 5
        assert call_args.kwargs["species"] is None


class TestDetectionAudio:
    """Test detection audio endpoint."""

    def test_get_detection_with_uuid(self, client, model_factory):
        """Should get detection with UUID and taxa enrichment."""
        mock_detection = model_factory.create_detection_with_taxa(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
            latitude=40.0,
            longitude=-74.0,
            species_confidence_threshold=0.5,
            week=3,
            sensitivity_setting=1.0,
            overlap=0.0,
            ioc_english_name="American Robin",
            translated_name="Robin",
            family="Turdidae",
            genus="Turdus",
            order_name="Passeriformes",
        )

        client.mock_query_service.get_detection_with_taxa = AsyncMock(return_value=mock_detection)

        response = client.get(f"/api/detections/{mock_detection.id}?language_code=en")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mock_detection.id)
        assert data["scientific_name"] == "Turdus migratorius"
        assert data["family"] == "Turdidae"
        assert data["genus"] == "Turdus"

    def test_get_detection_uuid_not_found(self, client):
        """Should return 404 for non-existent UUID detection."""
        client.mock_query_service.get_detection_with_taxa = AsyncMock(return_value=None)
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        response = client.get(f"/api/detections/{uuid4()}")

        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]

    def test_get_detection_audio_success(self, client, tmp_path, model_factory):
        """Should successfully serve audio file when detection and file exist."""
        # Create a temporary WAV file
        audio_file_path = tmp_path / "test_audio.wav"
        audio_file_path.write_bytes(
            b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 100
        )  # Minimal WAV header

        # Create a detection with audio file
        mock_detection = model_factory.create_detection()
        mock_detection.audio_file = MagicMock()
        mock_detection.audio_file.file_path = audio_file_path

        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)

        response = client.get(f"/api/detections/{mock_detection.id}/audio")

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["cache-control"] == "public, max-age=3600"
        assert response.headers["accept-ranges"] == "bytes"
        assert len(response.content) > 0

    def test_get_detection_audio_not_found(self, client):
        """Should return 404 when detection doesn't exist."""
        detection_id = uuid4()
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        response = client.get(f"/api/detections/{detection_id}/audio")

        assert response.status_code == 404
        assert f"Detection {detection_id} not found" in response.json()["detail"]

    def test_get_detection_audio_no_file_record(self, client, model_factory):
        """Should return 404 when detection has no audio file record."""
        mock_detection = model_factory.create_detection()
        mock_detection.audio_file = None

        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)

        response = client.get(f"/api/detections/{mock_detection.id}/audio")

        assert response.status_code == 404
        assert "Audio file not available" in response.json()["detail"]

    def test_get_detection_audio_file_missing(self, client, model_factory):
        """Should return 404 when audio file doesn't exist on disk."""
        # Create a detection with non-existent audio file path
        mock_detection = model_factory.create_detection()
        mock_detection.audio_file = MagicMock()
        mock_detection.audio_file.file_path = Path("/non/existent/audio.wav")

        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)

        response = client.get(f"/api/detections/{mock_detection.id}/audio")

        assert response.status_code == 404
        assert "Audio file not found on disk" in response.json()["detail"]

    def test_get_detection_audio_absolute_path(self, client, tmp_path, model_factory):
        """Should serve audio file with absolute path."""
        # Create a temporary WAV file with absolute path
        audio_file_path = tmp_path / "test_absolute.wav"
        audio_file_path.write_bytes(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 100)

        # Create detection with absolute path
        mock_detection = model_factory.create_detection()
        mock_detection.audio_file = MagicMock()
        mock_detection.audio_file.file_path = audio_file_path  # Absolute path

        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)

        response = client.get(f"/api/detections/{mock_detection.id}/audio")

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0

    def test_get_detection_audio_error_handling(self, client, model_factory):
        """Should handle unexpected errors when serving audio."""
        mock_detection = model_factory.create_detection()

        # Simulate unexpected exception
        client.mock_data_manager.get_detection_by_id = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        response = client.get(f"/api/detections/{mock_detection.id}/audio")

        assert response.status_code == 500
        assert "Error serving audio file" in response.json()["detail"]


class TestSpeciesSummary:
    """Test species and family summary endpoints."""

    def test_get_species_summary(self, client):
        """Should return species summary with counts."""
        mock_summary = [
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "family": "Turdidae",
                "genus": "Turdus",
                "count": 42,
            },
            {
                "scientific_name": "Corvus corax",
                "common_name": "Common Raven",
                "family": "Corvidae",
                "genus": "Corvus",
                "count": 15,
            },
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/species/summary?language_code=en")

        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 2
        assert data["count"] == 2
        assert data["species"][0]["detection_count"] == 42

    def test_get_species_summary_with_family_filter(self, client):
        """Should filter species summary by family."""
        mock_summary = [
            {
                "scientific_name": "Corvus corax",
                "common_name": "Common Raven",
                "family": "Corvidae",
                "count": 15,
            },
            {
                "scientific_name": "Corvus brachyrhynchos",
                "common_name": "American Crow",
                "family": "Corvidae",
                "count": 28,
            },
            {
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "family": "Turdidae",
                "count": 42,
            },
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/species/summary?family_filter=Corvidae")

        assert response.status_code == 200
        data = response.json()
        # The mock returns all species regardless of filter, so we get all 3
        assert len(data["species"]) == 3

    def test_get_species_summary_error(self, client):
        """Should handle errors in species summary."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/species/summary")

        assert response.status_code == 500
        assert "Error retrieving species summary" in response.json()["detail"]

    def test_get_species_summary_with_period_day(self, client):
        """Should return species summary for day period."""
        mock_summary = [
            {
                "scientific_name": "Turdus migratorius",
                "best_common_name": "American Robin",
                "detection_count": 10,
                "family": "Turdidae",
                "genus": "Turdus",
                "order_name": "Passeriformes",
                "first_ever_detection": None,
            }
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/species/summary?period=day")

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "day"
        assert data["period_label"] == "Today"
        assert len(data["species"]) == 1

    def test_get_species_summary_with_period_week(self, client):
        """Should return species summary for week period."""
        client.mock_query_service.get_species_summary = AsyncMock(return_value=[])

        response = client.get("/api/detections/species/summary?period=week")

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "week"
        assert data["period_label"] == "This Week"

    def test_get_species_summary_with_period_historical(self, client):
        """Should return species summary for historical period."""
        mock_summary = [
            {
                "scientific_name": "Corvus corax",
                "best_common_name": "Common Raven",
                "detection_count": 250,
                "first_ever_detection": datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            }
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/species/summary?period=historical")

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "historical"
        assert data["period_label"] == "All Time"
        # Should call with since=None for historical
        client.mock_query_service.get_species_summary.assert_called_once()

    def test_get_species_summary_first_ever_detection(self, client):
        """Should correctly set is_first_ever flag."""
        first_detection_time = datetime(2025, 1, 10, 10, 0, 0, tzinfo=UTC)
        mock_summary = [
            {
                "scientific_name": "Rare Bird",
                "best_common_name": "Very Rare Bird",
                "detection_count": 1,
                "first_ever_detection": first_detection_time,
            }
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/species/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["species"][0]["is_first_ever"] is True
        assert data["species"][0]["first_ever_detection"] is not None


class TestDetectionStreaming:
    """Test SSE streaming endpoint helper functions."""

    def test_format_detection_event(self, model_factory):
        """Should format detection as SSE event correctly."""
        mock_detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            latitude=40.0,
            longitude=-74.0,
        )

        event_data = _format_detection_event(mock_detection)

        assert event_data["id"] == str(mock_detection.id)
        assert event_data["scientific_name"] == "Turdus migratorius"
        assert event_data["common_name"] == "American Robin"
        assert event_data["confidence"] == 0.95
        assert event_data["latitude"] == 40.0
        assert event_data["longitude"] == -74.0
        # Timestamp should have Z suffix for UTC
        assert event_data["timestamp"].endswith("Z")

    def test_create_detection_handler(self, model_factory):
        """Should create detection handler for SSE."""
        # Create an event loop and queue
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()

        # Create handler
        handler = _create_detection_handler(loop, queue)

        # Test that handler is callable
        assert callable(handler)

        # Create a mock detection
        mock_detection = model_factory.create_detection(scientific_name="Test Bird")

        # Call handler (simulating signal emission)
        handler(sender=None, detection=mock_detection)

        # Queue should have the detection
        # Note: can't easily test without running the event loop
        loop.close()


class TestDetectionsSummary:
    """Test detections summary endpoint with period filtering."""

    def test_get_summary_day_period(self, client):
        """Should return summary for current day."""
        mock_summary = [
            {
                "scientific_name": "Turdus migratorius",
                "best_common_name": "American Robin",
                "ioc_english_name": "American Robin",
                "detection_count": 42,
            },
            {
                "scientific_name": "Corvus corax",
                "best_common_name": "Common Raven",
                "ioc_english_name": "Common Raven",
                "detection_count": 15,
            },
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)
        client.mock_query_service.get_detection_count = AsyncMock(return_value=57)

        response = client.get("/api/detections/summary?period=day")

        assert response.status_code == 200
        data = response.json()
        assert data["species_count"] == 2
        assert data["total_detections"] == 57
        assert len(data["species_frequency"]) == 2
        assert data["species_frequency"][0]["species"] == "American Robin"
        assert data["species_frequency"][0]["count"] == 42
        # 42/57 * 100 = 73.7%
        assert 73.0 <= data["species_frequency"][0]["percentage"] <= 74.0

    def test_get_summary_week_period(self, client):
        """Should return summary for current week."""
        mock_summary = [
            {
                "scientific_name": "Passer domesticus",
                "best_common_name": "House Sparrow",
                "ioc_english_name": "House Sparrow",
                "detection_count": 128,
            }
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)
        client.mock_query_service.get_detection_count = AsyncMock(return_value=128)

        response = client.get("/api/detections/summary?period=week")

        assert response.status_code == 200
        data = response.json()
        assert data["species_count"] == 1
        assert data["total_detections"] == 128

    def test_get_summary_month_period(self, client):
        """Should return summary for current month."""
        client.mock_query_service.get_species_summary = AsyncMock(return_value=[])
        client.mock_query_service.get_detection_count = AsyncMock(return_value=0)

        response = client.get("/api/detections/summary?period=month")

        assert response.status_code == 200
        data = response.json()
        assert data["species_count"] == 0
        assert data["total_detections"] == 0
        assert data["species_frequency"] == []

    def test_get_summary_historical_period(self, client):
        """Should return all-time summary for historical period."""
        mock_summary = [
            {
                "scientific_name": "Turdus migratorius",
                "best_common_name": "American Robin",
                "detection_count": 500,
            },
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)
        client.mock_query_service.get_detection_count = AsyncMock(return_value=500)

        response = client.get("/api/detections/summary?period=historical")

        assert response.status_code == 200
        data = response.json()
        assert data["total_detections"] == 500
        # Historical uses None for since parameter
        client.mock_query_service.get_species_summary.assert_called_once()
        call_kwargs = client.mock_query_service.get_species_summary.call_args.kwargs
        assert call_kwargs.get("since") is None

    def test_get_summary_error_handling(self, client):
        """Should handle errors gracefully."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/summary?period=day")

        assert response.status_code == 500
        assert "Failed to get detection summary" in response.json()["detail"]


class TestHierarchicalFiltering:
    """Test the hierarchical filtering endpoints for family/genus/species."""

    def test_get_families(self, client):
        """Should getting list of families."""
        # Mock the query service response
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
                {
                    "family": "Corvidae",
                    "genus": "Cyanocitta",
                    "scientific_name": "Cyanocitta cristata",
                },
                {"family": "Turdidae", "genus": "Turdus", "scientific_name": "Turdus migratorius"},
            ]
        )

        response = client.get("/api/detections/taxonomy/families")

        assert response.status_code == 200
        data = response.json()
        families = data["families"]
        assert len(families) == 2
        assert "Corvidae" in families
        assert "Turdidae" in families
        assert data["count"] == 2

    def test_get_genera_by_family(self, client):
        """Should getting genera for a specific family."""
        # Mock the query service response
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
                {
                    "family": "Corvidae",
                    "genus": "Cyanocitta",
                    "scientific_name": "Cyanocitta cristata",
                },
                {"family": "Turdidae", "genus": "Turdus", "scientific_name": "Turdus migratorius"},
            ]
        )

        response = client.get("/api/detections/taxonomy/genera?family=Corvidae")

        assert response.status_code == 200
        data = response.json()
        genera = data["genera"]
        assert len(genera) == 2
        assert "Corvus" in genera
        assert "Cyanocitta" in genera
        assert data["family"] == "Corvidae"
        assert data["count"] == 2

    def test_get_species_by_genus(self, client):
        """Should getting species for a specific genus."""
        # Mock the query service response
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {
                    "family": "Corvidae",
                    "genus": "Cyanocitta",
                    "scientific_name": "Cyanocitta cristata",
                    "best_common_name": "Blue Jay",
                    "ioc_english_name": "Blue Jay",
                    "detection_count": 42,
                },
                {
                    "family": "Corvidae",
                    "genus": "Corvus",
                    "scientific_name": "Corvus corax",
                    "best_common_name": "Common Raven",
                    "ioc_english_name": "Common Raven",
                    "detection_count": 15,
                },
            ]
        )

        response = client.get("/api/detections/taxonomy/species?genus=Cyanocitta")

        assert response.status_code == 200
        data = response.json()
        species = data["species"]
        assert len(species) == 1
        assert species[0]["scientific_name"] == "Cyanocitta cristata"
        assert species[0]["common_name"] == "Blue Jay"
        assert species[0]["count"] == 42
        assert data["genus"] == "Cyanocitta"
        assert data["count"] == 1

    def test_get_species_by_genus_with_family_filter(self, client):
        """Should getting species for a genus filtered by family."""
        # Mock the query service response
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {
                    "family": "Corvidae",
                    "genus": "Corvus",
                    "scientific_name": "Corvus corax",
                    "best_common_name": "Common Raven",
                    "ioc_english_name": "Common Raven",
                    "detection_count": 15,
                },
                {
                    "family": "Corvidae",
                    "genus": "Corvus",
                    "scientific_name": "Corvus brachyrhynchos",
                    "best_common_name": "American Crow",
                    "ioc_english_name": "American Crow",
                    "detection_count": 28,
                },
            ]
        )

        response = client.get("/api/detections/taxonomy/species?genus=Corvus&family=Corvidae")

        assert response.status_code == 200
        data = response.json()
        species = data["species"]
        assert len(species) == 2
        assert all(s["scientific_name"].startswith("Corvus") for s in species)
        assert data["genus"] == "Corvus"
        assert data["family"] == "Corvidae"

    def test_get_families_empty_result(self, client):
        """Should getting families when no detections exist."""
        client.mock_query_service.get_species_summary = AsyncMock(return_value=[])

        response = client.get("/api/detections/taxonomy/families")

        assert response.status_code == 200
        data = response.json()
        assert data["families"] == []
        assert data["count"] == 0

    def test_get_genera_unknown_family(self, client):
        """Should getting genera for a family with no detections."""
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
            ]
        )

        response = client.get("/api/detections/taxonomy/genera?family=UnknownFamily")

        assert response.status_code == 200
        data = response.json()
        assert data["genera"] == []
        assert data["family"] == "UnknownFamily"
        assert data["count"] == 0

    def test_get_species_unknown_genus(self, client):
        """Should getting species for a genus with no detections."""
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
            ]
        )

        response = client.get("/api/detections/taxonomy/species?genus=UnknownGenus")

        assert response.status_code == 200
        data = response.json()
        assert data["species"] == []
        assert data["genus"] == "UnknownGenus"
        assert data["count"] == 0

    def test_get_families_error(self, client):
        """Should handle errors when getting families."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/taxonomy/families")

        assert response.status_code == 500
        assert "Error retrieving families" in response.json()["detail"]

    def test_get_genera_error(self, client):
        """Should handle errors when getting genera."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/taxonomy/genera?family=Corvidae")

        assert response.status_code == 500
        assert "Error retrieving genera" in response.json()["detail"]

    def test_get_species_error(self, client):
        """Should handle errors when getting species."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/taxonomy/species?genus=Corvus")

        assert response.status_code == 500
        assert "Error retrieving species" in response.json()["detail"]

    def test_get_families_without_detection_filter(self, client):
        """Should handle has_detections=false parameter."""
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
            ]
        )

        response = client.get("/api/detections/taxonomy/families?has_detections=false")

        assert response.status_code == 200
        data = response.json()
        # Currently returns same as has_detections=true (would need IOC database)
        assert "families" in data

    def test_get_genera_without_detection_filter(self, client):
        """Should handle has_detections=false parameter for genera."""
        client.mock_query_service.get_species_summary = AsyncMock(
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
            ]
        )

        response = client.get(
            "/api/detections/taxonomy/genera?family=Corvidae&has_detections=false"
        )

        assert response.status_code == 200
        data = response.json()
        assert "genera" in data
        assert data["family"] == "Corvidae"
