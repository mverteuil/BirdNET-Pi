"""Tests for detections API routes that handle detection CRUD operations and spectrograms."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.queries import DetectionQueryService
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
    mock_query_service = MagicMock(spec=DetectionQueryService)
    # PlottingManager has been removed from the codebase

    # Add query_service attribute to the mock data manager
    mock_data_manager.query_service = None

    container.data_manager.override(mock_data_manager)
    container.detection_query_service.override(mock_query_service)
    # container.plotting_manager.override() - removed as PlottingManager no longer exists

    # Mock the config dependency
    from birdnetpi.config.models import BirdNETConfig

    mock_config = MagicMock(spec=BirdNETConfig)
    mock_config.language = "en"
    container.config.override(mock_config)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])

    # Include the router
    app.include_router(router, prefix="/api/detections")

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_data_manager = mock_data_manager  # type: ignore[attr-defined]
    client.mock_query_service = mock_query_service  # type: ignore[attr-defined]
    client.mock_config = mock_config  # type: ignore[attr-defined]
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

    def test_get_recent_detections(self, client):
        """Should return recent detections."""
        # Mock DetectionWithTaxa objects with required attributes
        mock_detections = [
            MagicMock(
                id=1,
                scientific_name="Turdus migratorius",
                common_name="Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30),
                latitude=40.0,
                longitude=-74.0,
                # DetectionWithTaxa specific attributes
                ioc_english_name="American Robin",
                translated_name="Robin",
                family="Turdidae",
                genus="Turdus",
                order_name="Passeriformes",
            ),
            MagicMock(
                id=2,
                scientific_name="Passer domesticus",
                common_name="Sparrow",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0),
                latitude=40.1,
                longitude=-74.1,
                # DetectionWithTaxa specific attributes
                ioc_english_name="House Sparrow",
                translated_name="Sparrow",
                family="Passeridae",
                genus="Passer",
                order_name="Passeriformes",
            ),
        ]
        # Mock query_detections on DetectionQueryService (not DataManager)
        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)
        # Mock get_species_display_name to return the common name
        client.mock_query_service.get_species_display_name = MagicMock(
            side_effect=lambda d, *args: d.common_name
        )

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
        from datetime import UTC, datetime

        today = datetime.now(UTC).date()
        client.mock_query_service.count_by_date = AsyncMock(return_value={today: 5})

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

        response = client.get("/api/detections/123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "123"  # API returns ID as string
        assert data["common_name"] == "Test Bird"

    def test_get_detection_by_id_not_found(self, client):
        """Should return 404 for non-existent detection."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        response = client.get("/api/detections/999")

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

    def test_update_detection_location_not_found(self, client):
        """Should return 404 when updating location of non-existent detection."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post("/api/detections/999/location", json=location_data)

        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]

    def test_update_detection_location_failed(self, client):
        """Should handle update failure."""
        mock_detection = MagicMock(id=123)
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=mock_detection)
        client.mock_data_manager.update_detection = AsyncMock(return_value=None)

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post("/api/detections/123/location", json=location_data)

        assert response.status_code == 500
        assert "Failed to update detection location" in response.json()["detail"]

    def test_update_detection_location_error(self, client):
        """Should handle unexpected errors in location update."""
        client.mock_data_manager.get_detection_by_id = AsyncMock(
            side_effect=Exception("Database error")
        )

        location_data = {"latitude": 41.0, "longitude": -75.0}

        response = client.post("/api/detections/123/location", json=location_data)

        assert response.status_code == 500
        assert "Error updating detection location" in response.json()["detail"]

    # Spectrogram tests removed - endpoint and PlottingManager have been removed from codebase


class TestPaginatedDetections:
    """Test paginated detections endpoint."""

    def test_get_paginated_detections(self, client):
        """Should return paginated detections."""
        # Mock DetectionWithTaxa objects
        mock_detections = [
            MagicMock(
                id=i,
                scientific_name=f"Species {i}",
                common_name=f"Common {i}",
                confidence=0.9,
                timestamp=datetime(2025, 1, 15, 10, i),
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
        client.mock_query_service.get_species_display_name = MagicMock(
            side_effect=lambda d, *args: f"Display {d.common_name}"
        )

        response = client.get("/api/detections/paginated?page=1&per_page=10&period=week")

        assert response.status_code == 200
        data = response.json()
        assert len(data["detections"]) == 10
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["per_page"] == 10
        assert data["pagination"]["total"] == 25
        assert data["pagination"]["total_pages"] == 3
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is False

    def test_get_paginated_detections_with_search(self, client):
        """Should filter paginated detections by search term."""
        # Mock detections with different names
        mock_detections = [
            MagicMock(
                id=1,
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30),
            ),
            MagicMock(
                id=2,
                scientific_name="Corvus corax",
                common_name="Common Raven",
                confidence=0.88,
                timestamp=datetime(2025, 1, 15, 11, 0),
            ),
            MagicMock(
                id=3,
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                confidence=0.92,
                timestamp=datetime(2025, 1, 15, 11, 30),
            ),
        ]

        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)
        client.mock_query_service.get_species_display_name = MagicMock(
            side_effect=lambda d, *args: d.common_name
        )

        # Search for "Robin"
        response = client.get("/api/detections/paginated?search=Robin")

        assert response.status_code == 200
        data = response.json()
        assert len(data["detections"]) == 1
        assert data["detections"][0]["species"] == "American Robin"

    def test_get_paginated_detections_empty_result(self, client):
        """Should handle empty results gracefully."""
        client.mock_query_service.query_detections = AsyncMock(return_value=[])

        response = client.get("/api/detections/paginated?page=1")

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

        response = client.get("/api/detections/paginated")

        assert response.status_code == 500
        assert "Error retrieving detections" in response.json()["detail"]


class TestBestRecordings:
    """Test best recordings endpoint."""

    def test_get_best_recordings(self, client):
        """Should return best recordings with highest confidence."""
        mock_detections = [
            MagicMock(
                id=1,
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                ioc_english_name="American Robin",
                confidence=0.98,
                timestamp=datetime(2025, 1, 15, 10, 30),
                family="Turdidae",
                genus="Turdus",
            ),
            MagicMock(
                id=2,
                scientific_name="Corvus corax",
                common_name="Common Raven",
                ioc_english_name="Common Raven",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 11, 0),
                family="Corvidae",
                genus="Corvus",
            ),
        ]

        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        response = client.get("/api/detections/best-recordings?min_confidence=0.9&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 2
        assert data["recordings"][0]["confidence"] == 98.0
        assert data["count"] == 2
        assert data["unique_species"] == 2
        assert data["avg_confidence"] > 0

    def test_get_best_recordings_with_family_filter(self, client):
        """Should filter best recordings by family."""
        mock_detections = [
            MagicMock(
                id=1,
                scientific_name="Corvus corax",
                common_name="Common Raven",
                ioc_english_name="Common Raven",
                confidence=0.95,
                timestamp=datetime(2025, 1, 15, 10, 30),
                family="Corvidae",
                genus="Corvus",
            ),
        ]

        client.mock_query_service.query_detections = AsyncMock(return_value=mock_detections)

        response = client.get("/api/detections/best-recordings?family=Corvidae")

        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 1
        assert data["recordings"][0]["family"] == "Corvidae"
        assert data["filters"]["family"] == "Corvidae"

    def test_get_best_recordings_empty(self, client):
        """Should handle empty results for best recordings."""
        client.mock_query_service.query_detections = AsyncMock(return_value=[])

        response = client.get("/api/detections/best-recordings?min_confidence=0.99")

        assert response.status_code == 200
        data = response.json()
        assert data["recordings"] == []
        assert data["count"] == 0
        assert data["avg_confidence"] == 0
        assert data["date_range"] == "No recordings"

    def test_get_best_recordings_error(self, client):
        """Should handle errors in best recordings."""
        client.mock_query_service.query_detections = AsyncMock(
            side_effect=Exception("Query failed")
        )

        response = client.get("/api/detections/best-recordings")

        assert response.status_code == 500
        assert "Error retrieving best recordings" in response.json()["detail"]


class TestDetectionAudio:
    """Test detection audio endpoint."""

    def test_get_detection_with_uuid(self, client):
        """Should get detection with UUID and taxa enrichment."""
        from uuid import uuid4

        detection_uuid = uuid4()
        mock_detection = MagicMock(
            id=detection_uuid,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 15, 10, 30),
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
        client.mock_query_service.get_species_display_name = MagicMock(
            return_value="American Robin"
        )

        response = client.get(f"/api/detections/{detection_uuid}?language_code=en")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(detection_uuid)
        assert data["scientific_name"] == "Turdus migratorius"
        assert data["family"] == "Turdidae"
        assert data["genus"] == "Turdus"

    def test_get_detection_uuid_not_found(self, client):
        """Should return 404 for non-existent UUID detection."""
        from uuid import uuid4

        client.mock_query_service.get_detection_with_taxa = AsyncMock(return_value=None)
        client.mock_data_manager.get_detection_by_id = AsyncMock(return_value=None)

        response = client.get(f"/api/detections/{uuid4()}")

        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]


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
        assert data["species"][0]["count"] == 42

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
        assert len(data["species"]) == 2
        assert all(s["family"] == "Corvidae" for s in data["species"])

    def test_get_species_summary_error(self, client):
        """Should handle errors in species summary."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/species/summary")

        assert response.status_code == 500
        assert "Error retrieving species summary" in response.json()["detail"]

    def test_get_family_summary(self, client):
        """Should return family summary with aggregated counts."""
        mock_summary = [
            {"family": "Corvidae", "genus": "Corvus", "count": 15},
            {"family": "Corvidae", "genus": "Cyanocitta", "count": 10},
            {"family": "Turdidae", "genus": "Turdus", "count": 42},
        ]

        client.mock_query_service.get_species_summary = AsyncMock(return_value=mock_summary)

        response = client.get("/api/detections/families/summary")

        assert response.status_code == 200
        data = response.json()
        assert len(data["families"]) == 2
        # Corvidae should have 15 + 10 = 25 total
        corvidae = next(f for f in data["families"] if f["family"] == "Corvidae")
        assert corvidae["count"] == 25
        # Turdidae should have 42
        turdidae = next(f for f in data["families"] if f["family"] == "Turdidae")
        assert turdidae["count"] == 42

    def test_get_family_summary_error(self, client):
        """Should handle errors in family summary."""
        client.mock_query_service.get_species_summary = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/detections/families/summary")

        assert response.status_code == 500
        assert "Error retrieving family summary" in response.json()["detail"]


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
