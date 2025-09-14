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

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.container = container  # type: ignore[attr-defined]

    # Include the router
    app.include_router(router, prefix="/api/detections")

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_data_manager = mock_data_manager  # type: ignore[attr-defined]
    client.mock_query_service = mock_query_service  # type: ignore[attr-defined]
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

    # Spectrogram tests removed - endpoint and PlottingManager have been removed from codebase


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
