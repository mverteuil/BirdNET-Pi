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
from birdnetpi.detections.models import AudioFile
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.detections_api_routes import (
    _create_detection_handler,
    _format_detection_event,
    router,
)


@pytest.fixture
def client(path_resolver, test_config, cache):
    """Create test client with detections API routes and mocked dependencies."""
    app = FastAPI()
    container = Container()
    mock_data_manager = MagicMock(spec=DataManager, query_service=None)
    mock_query_service = MagicMock(spec=DetectionQueryService)
    container.data_manager.override(mock_data_manager)
    container.detection_query_service.override(mock_query_service)
    container.config.override(test_config)
    container.cache_service.override(cache)
    container.wire(modules=["birdnetpi.web.routers.detections_api_routes"])
    app.include_router(router, prefix="/api")
    client = TestClient(app)
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
        client.mock_data_manager.create_detection = AsyncMock(
            spec=DataManager.create_detection, return_value=mock_detection
        )
        test_audio = base64.b64encode(b"test audio data").decode("utf-8")
        detection_data = {
            "species_tensor": "Testus species_Test Bird",
            "scientific_name": "Testus species",
            "common_name": "Test Bird",
            "confidence": 0.95,
            "timestamp": "2025-01-15T10:30:00",
            "audio_data": test_audio,
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
        detection_data = {
            "species_tensor": "Testus species_Test Bird",
            "scientific_name": "Testus species",
        }
        response = client.post("/api/detections/", json=detection_data)
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_get_recent_detections(self, client, model_factory):
        """Should return recent detections."""
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
        client.mock_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
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
            spec=DetectionQueryService.query_detections, side_effect=Exception("Database error")
        )
        response = client.get("/api/detections/recent?limit=10")
        assert response.status_code == 500
        assert "Error retrieving recent detections" in response.json()["detail"]

    @pytest.mark.parametrize(
        "target_date,mock_return,expected_count,expected_date",
        [
            # SQLite's date() function returns ISO date strings, not date objects
            pytest.param(
                None, lambda: {datetime.now(UTC).date().isoformat(): 5}, 5, None, id="today-default"
            ),
            pytest.param(
                date(2025, 1, 15),
                lambda: {"2025-01-15": 42},
                42,
                "2025-01-15",
                id="specific-date",
            ),
            pytest.param(date(2020, 1, 1), lambda: {}, 0, None, id="zero-detections"),
        ],
    )
    def test_get_detection_count(
        self, client, target_date, mock_return, expected_count, expected_date
    ):
        """Should return detection count for various date scenarios."""
        client.mock_query_service.count_by_date = AsyncMock(
            spec=DetectionQueryService.count_by_date, return_value=mock_return()
        )

        url = "/api/detections/count"
        if target_date:
            url += f"?target_date={target_date.isoformat()}"

        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == expected_count
        if expected_date:
            assert data["date"] == expected_date

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
        client.mock_query_service.get_detection_with_taxa = AsyncMock(
            spec=DetectionQueryService.get_detection_with_taxa, return_value=mock_detection
        )
        response = client.get(f"/api/detections/{mock_detection.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"]
        assert data["common_name"] == "Test Bird"

    def test_get_detection_by_id_not_found(self, client):
        """Should return 404 for non-existent detection."""
        client.mock_query_service.get_detection_with_taxa = AsyncMock(
            spec=DetectionQueryService.get_detection_with_taxa, return_value=None
        )
        response = client.get(f"/api/detections/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "get_detection_return,update_return,get_error,update_error,expected_status,expected_message",
        [
            pytest.param(
                "mock_detection",
                "updated_detection",
                None,
                None,
                200,
                "Location updated successfully",
                id="success",
            ),
            pytest.param(None, None, None, None, 404, "Detection not found", id="not-found"),
            pytest.param(
                "mock_detection",
                None,
                None,
                None,
                500,
                "Failed to update detection location",
                id="update-failed",
            ),
            pytest.param(
                None,
                None,
                Exception("Database error"),
                None,
                500,
                "Error updating detection location",
                id="database-error",
            ),
        ],
    )
    def test_update_detection_location(
        self,
        client,
        model_factory,
        get_detection_return,
        update_return,
        get_error,
        update_error,
        expected_status,
        expected_message,
    ):
        """Should handle various scenarios when updating detection location."""
        detection_id = uuid4()

        if get_detection_return == "mock_detection":
            mock_detection = model_factory.create_detection(id=detection_id)
            get_return = mock_detection
        else:
            get_return = get_detection_return

        if update_return == "updated_detection":
            updated_detection = model_factory.create_detection(
                id=detection_id, latitude=40.1, longitude=-74.1
            )
            upd_return = updated_detection
        else:
            upd_return = update_return

        if get_error:
            client.mock_data_manager.get_detection_by_id = AsyncMock(
                spec=DataManager.get_detection_by_id, side_effect=get_error
            )
        else:
            client.mock_data_manager.get_detection_by_id = AsyncMock(
                spec=DataManager.get_detection_by_id, return_value=get_return
            )

        if update_error:
            client.mock_data_manager.update_detection = AsyncMock(
                spec=DataManager.update_detection, side_effect=update_error
            )
        else:
            client.mock_data_manager.update_detection = AsyncMock(
                spec=DataManager.update_detection, return_value=upd_return
            )

        location_data = {"latitude": 41.0, "longitude": -75.0}
        response = client.post(f"/api/detections/{detection_id}/location", json=location_data)
        assert response.status_code == expected_status
        assert expected_message in response.json().get("detail", response.json().get("message", ""))


class TestPaginatedDetections:
    """Test paginated detections endpoint."""

    def test_get_paginated_detections(self, client, model_factory):
        """Should return paginated detections."""
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
            for i in range(25)
        ]
        client.mock_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
        )
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
        client.mock_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
        )
        response = client.get("/api/detections/?search=Robin")
        assert response.status_code == 200
        data = response.json()
        assert len(data["detections"]) == 1
        assert data["detections"][0]["common_name"] == "American Robin (Turdus migratorius)"

    @pytest.mark.parametrize(
        "mock_return,expected_status,expected_error",
        [
            pytest.param([], 200, None, id="empty-result"),
            pytest.param(
                Exception("Database error"),
                500,
                "Error retrieving detections",
                id="database-error",
            ),
        ],
    )
    def test_get_paginated_detections_scenarios(
        self, client, mock_return, expected_status, expected_error
    ):
        """Should handle various scenarios for paginated detections."""
        if isinstance(mock_return, Exception):
            client.mock_query_service.query_detections = AsyncMock(
                spec=DetectionQueryService.query_detections, side_effect=mock_return
            )
        else:
            client.mock_query_service.query_detections = AsyncMock(
                spec=DetectionQueryService.query_detections, return_value=mock_return
            )

        response = client.get("/api/detections/?page=1&per_page=10")
        assert response.status_code == expected_status

        if expected_status == 200:
            data = response.json()
            assert data["detections"] == []
            assert data["pagination"]["total"] == 0
            assert data["pagination"]["total_pages"] == 0
        else:
            assert expected_error in response.json()["detail"]

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
        client.mock_query_service.query_detections = AsyncMock(
            spec=DetectionQueryService.query_detections, return_value=mock_detections
        )
        response = client.get("/api/detections/?page=1&per_page=20")
        assert response.status_code == 200
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
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            spec=DetectionQueryService.query_best_recordings_per_species,
            return_value=(mock_detections, len(mock_detections)),
        )
        response = client.get(
            "/api/detections/best-recordings?min_confidence=0.9&page=1&per_page=50"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 2
        assert data["recordings"][0]["confidence"] == 0.98
        assert data["count"] == 2
        assert data["unique_species"] == 2
        assert data["avg_confidence"] > 0
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["total"] == 2
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
            )
        ]
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            spec=DetectionQueryService.query_best_recordings_per_species,
            return_value=(mock_detections, 1),
        )
        response = client.get("/api/detections/best-recordings?family=Corvidae")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recordings"]) == 1
        assert data["recordings"][0]["family"] == "Corvidae"
        assert data["filters"]["family"] == "Corvidae"

    @pytest.mark.parametrize(
        "mock_return,expected_status,expected_error",
        [
            pytest.param(([], 0), 200, None, id="empty-results"),
            pytest.param(
                Exception("Query failed"),
                500,
                "Error retrieving best recordings",
                id="database-error",
            ),
        ],
    )
    def test_get_best_recordings_scenarios(
        self, client, mock_return, expected_status, expected_error
    ):
        """Should handle various scenarios for best recordings."""
        if isinstance(mock_return, Exception):
            client.mock_query_service.query_best_recordings_per_species = AsyncMock(
                spec=DetectionQueryService.query_best_recordings_per_species,
                side_effect=mock_return,
            )
        else:
            client.mock_query_service.query_best_recordings_per_species = AsyncMock(
                spec=DetectionQueryService.query_best_recordings_per_species,
                return_value=mock_return,
            )

        response = client.get("/api/detections/best-recordings?min_confidence=0.99")
        assert response.status_code == expected_status

        if expected_status == 200:
            data = response.json()
            assert data["recordings"] == []
            assert data["count"] == 0
            assert data["avg_confidence"] == 0
            assert data["date_range"] == "No recordings"
        else:
            assert expected_error in response.json()["detail"]

    def test_get_best_recordings_with_species_filter_no_limit(self, client, model_factory):
        """Should pass None per_species_limit when species filter is provided."""
        mock_detection = model_factory.create_detection_with_taxa(
            scientific_name="Turdus migratorius", common_name="American Robin", confidence=0.95
        )
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            spec=DetectionQueryService.query_best_recordings_per_species,
            return_value=([mock_detection], 1),
        )
        response = client.get("/api/detections/best-recordings?species=Turdus%20migratorius")
        assert response.status_code == 200
        client.mock_query_service.query_best_recordings_per_species.assert_called_once()
        call_args = client.mock_query_service.query_best_recordings_per_species.call_args
        assert call_args.kwargs["per_species_limit"] is None
        assert call_args.kwargs["species"] == "Turdus migratorius"

    def test_get_best_recordings_without_species_uses_default_limit(self, client, model_factory):
        """Should use default per_species_limit when no species filter."""
        mock_detection = model_factory.create_detection_with_taxa(
            scientific_name="Turdus migratorius", common_name="American Robin", confidence=0.95
        )
        client.mock_query_service.query_best_recordings_per_species = AsyncMock(
            spec=DetectionQueryService.query_best_recordings_per_species,
            return_value=([mock_detection], 1),
        )
        response = client.get("/api/detections/best-recordings")
        assert response.status_code == 200
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
        client.mock_query_service.get_detection_with_taxa = AsyncMock(
            spec=DetectionQueryService.get_detection_with_taxa, return_value=mock_detection
        )
        response = client.get(f"/api/detections/{mock_detection.id}?language_code=en")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mock_detection.id)
        assert data["scientific_name"] == "Turdus migratorius"
        assert data["family"] == "Turdidae"
        assert data["genus"] == "Turdus"

    def test_get_detection_uuid_not_found(self, client):
        """Should return 404 for non-existent UUID detection."""
        client.mock_query_service.get_detection_with_taxa = AsyncMock(
            spec=DetectionQueryService.get_detection_with_taxa, return_value=None
        )
        client.mock_data_manager.get_detection_by_id = AsyncMock(
            spec=DataManager.get_detection_by_id, return_value=None
        )
        response = client.get(f"/api/detections/{uuid4()}")
        assert response.status_code == 404
        assert "Detection not found" in response.json()["detail"]

    @pytest.mark.parametrize(
        "audio_file_state,file_exists,side_effect,expected_status,expected_message",
        [
            pytest.param("valid", True, None, 200, None, id="success"),
            pytest.param(None, False, None, 404, "Detection .* not found", id="no-detection"),
            pytest.param(
                "no_file", False, None, 404, "Audio file not available", id="no-audio-record"
            ),
            pytest.param(
                "missing", False, None, 404, "Audio file not found on disk", id="file-missing"
            ),
            pytest.param("valid", True, None, 200, None, id="absolute-path"),
            pytest.param(
                None,
                False,
                Exception("Unexpected error"),
                500,
                "Error serving audio file",
                id="error",
            ),
        ],
    )
    def test_get_detection_audio(
        self,
        client,
        tmp_path,
        model_factory,
        audio_file_state,
        file_exists,
        side_effect,
        expected_status,
        expected_message,
    ):
        """Should handle various scenarios when serving detection audio."""
        detection_id = uuid4()

        if audio_file_state == "valid":
            audio_file_path = tmp_path / "test_audio.wav"
            if file_exists:
                audio_file_path.write_bytes(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 100)
            mock_detection = model_factory.create_detection(id=detection_id)
            mock_detection.audio_file = MagicMock(spec=AudioFile)
            mock_detection.audio_file.file_path = audio_file_path
            detection_return = mock_detection
        elif audio_file_state == "no_file":
            mock_detection = model_factory.create_detection(id=detection_id)
            mock_detection.audio_file = None
            detection_return = mock_detection
        elif audio_file_state == "missing":
            mock_detection = model_factory.create_detection(id=detection_id)
            mock_detection.audio_file = MagicMock(spec=AudioFile)
            mock_detection.audio_file.file_path = Path("/non/existent/audio.wav")
            detection_return = mock_detection
        else:
            detection_return = None

        if side_effect:
            client.mock_data_manager.get_detection_by_id = AsyncMock(
                spec=DataManager.get_detection_by_id, side_effect=side_effect
            )
        else:
            client.mock_data_manager.get_detection_by_id = AsyncMock(
                spec=DataManager.get_detection_by_id, return_value=detection_return
            )

        response = client.get(f"/api/detections/{detection_id}/audio")
        assert response.status_code == expected_status

        if expected_status == 200:
            assert response.headers["content-type"] == "audio/wav"
            assert response.headers["cache-control"] == "public, max-age=3600"
            assert response.headers["accept-ranges"] == "bytes"
            assert len(response.content) > 0
        else:
            import re

            detail = response.json()["detail"]
            assert re.search(expected_message, detail), (
                f"Expected '{expected_message}' in '{detail}'"
            )


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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, return_value=mock_summary
        )
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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, return_value=mock_summary
        )
        response = client.get("/api/detections/species/summary?family_filter=Corvidae")
        assert response.status_code == 200
        data = response.json()
        assert len(data["species"]) == 3

    def test_get_species_summary_error(self, client):
        """Should handle errors in species summary."""
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, side_effect=Exception("Database error")
        )
        response = client.get("/api/detections/species/summary")
        assert response.status_code == 500
        assert "Error retrieving species summary" in response.json()["detail"]

    @pytest.mark.parametrize(
        "period,expected_label,has_first_detection",
        [
            pytest.param("day", "Today", False, id="day-period"),
            pytest.param("week", "This Week", False, id="week-period"),
            pytest.param("historical", "All Time", True, id="historical-period"),
        ],
    )
    def test_get_species_summary_with_period(
        self, client, period, expected_label, has_first_detection
    ):
        """Should return species summary for different periods."""
        mock_summary = (
            [
                {
                    "scientific_name": "Turdus migratorius"
                    if period != "historical"
                    else "Corvus corax",
                    "best_common_name": "American Robin"
                    if period != "historical"
                    else "Common Raven",
                    "detection_count": 10 if period == "day" else 250,
                    "family": "Turdidae" if period == "day" else None,
                    "genus": "Turdus" if period == "day" else None,
                    "order_name": "Passeriformes" if period == "day" else None,
                    "first_ever_detection": (
                        datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC) if has_first_detection else None
                    ),
                }
            ]
            if period != "week"
            else []
        )

        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, return_value=mock_summary
        )
        response = client.get(f"/api/detections/species/summary?period={period}")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == period
        assert data["period_label"] == expected_label
        if period != "week":
            assert len(data["species"]) == 1
        else:
            assert len(data["species"]) == 0
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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, return_value=mock_summary
        )
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
        assert event_data["timestamp"].endswith("Z")

    def test_create_detection_handler(self, model_factory):
        """Should create detection handler for SSE."""
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = _create_detection_handler(loop, queue)
        assert callable(handler)
        mock_detection = model_factory.create_detection(scientific_name="Test Bird")
        handler(sender=None, detection=mock_detection)
        loop.close()


class TestDetectionsSummary:
    """Test detections summary endpoint with period filtering."""

    @pytest.mark.parametrize(
        "period,detection_count,expected_count",
        [
            pytest.param("day", 57, 57, id="day-period"),
            pytest.param("week", 128, 128, id="week-period"),
            pytest.param("month", 0, 0, id="month-period"),
            pytest.param("historical", 500, 500, id="historical-period"),
        ],
    )
    def test_get_summary_period(self, client, period, detection_count, expected_count):
        """Should return summary for different periods."""
        if period == "day":
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
        elif period == "week":
            mock_summary = [
                {
                    "scientific_name": "Passer domesticus",
                    "best_common_name": "House Sparrow",
                    "ioc_english_name": "House Sparrow",
                    "detection_count": 128,
                }
            ]
        elif period == "historical":
            mock_summary = [
                {
                    "scientific_name": "Turdus migratorius",
                    "best_common_name": "American Robin",
                    "detection_count": 500,
                }
            ]
        else:  # month
            mock_summary = []

        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, return_value=mock_summary
        )
        client.mock_query_service.get_detection_count = AsyncMock(
            spec=DetectionQueryService.get_detection_count, return_value=detection_count
        )

        response = client.get(f"/api/detections/summary?period={period}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_detections"] == expected_count

        if period == "day":
            assert data["species_count"] == 2
            assert len(data["species_frequency"]) == 2
            assert data["species_frequency"][0]["species"] == "American Robin"
            assert data["species_frequency"][0]["count"] == 42
            assert 73.0 <= data["species_frequency"][0]["percentage"] <= 74.0
        elif period == "week":
            assert data["species_count"] == 1
        elif period == "month":
            assert data["species_count"] == 0
            assert data["species_frequency"] == []
        else:  # historical
            assert data["total_detections"] == 500
            call_kwargs = client.mock_query_service.get_species_summary.call_args.kwargs
            assert call_kwargs.get("since") is None

    def test_get_summary_error_handling(self, client):
        """Should handle errors gracefully."""
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary, side_effect=Exception("Database error")
        )
        response = client.get("/api/detections/summary?period=day")
        assert response.status_code == 500
        assert "Failed to get detection summary" in response.json()["detail"]


class TestAPIErrorHandling:
    """Test error handling across all API endpoints."""

    @pytest.mark.parametrize(
        "endpoint,mock_method,expected_message",
        [
            pytest.param(
                "/api/detections/taxonomy/families",
                "get_species_summary",
                "Error retrieving families",
                id="families-error",
            ),
            pytest.param(
                "/api/detections/taxonomy/genera?family=Corvidae",
                "get_species_summary",
                "Error retrieving genera",
                id="genera-error",
            ),
            pytest.param(
                "/api/detections/taxonomy/species?genus=Corvus",
                "get_species_summary",
                "Error retrieving species",
                id="species-error",
            ),
        ],
    )
    def test_taxonomy_endpoint_errors(self, client, endpoint, mock_method, expected_message):
        """Should handle errors in taxonomy endpoints consistently."""
        setattr(
            client.mock_query_service,
            mock_method,
            AsyncMock(
                spec=getattr(DetectionQueryService, mock_method),
                side_effect=Exception("Database error"),
            ),
        )
        response = client.get(endpoint)
        assert response.status_code == 500
        assert expected_message in response.json()["detail"]


class TestHierarchicalFiltering:
    """Test the hierarchical filtering endpoints for family/genus/species."""

    def test_get_families(self, client):
        """Should getting list of families."""
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
                {
                    "family": "Corvidae",
                    "genus": "Cyanocitta",
                    "scientific_name": "Cyanocitta cristata",
                },
                {"family": "Turdidae", "genus": "Turdus", "scientific_name": "Turdus migratorius"},
            ],
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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"},
                {
                    "family": "Corvidae",
                    "genus": "Cyanocitta",
                    "scientific_name": "Cyanocitta cristata",
                },
                {"family": "Turdidae", "genus": "Turdus", "scientific_name": "Turdus migratorius"},
            ],
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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
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
            ],
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
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
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
            ],
        )
        response = client.get("/api/detections/taxonomy/species?genus=Corvus&family=Corvidae")
        assert response.status_code == 200
        data = response.json()
        species = data["species"]
        assert len(species) == 2
        assert all(s["scientific_name"].startswith("Corvus") for s in species)
        assert data["genus"] == "Corvus"
        assert data["family"] == "Corvidae"

    @pytest.mark.parametrize(
        "endpoint,params,field,filter_value",
        [
            pytest.param(
                "/api/detections/taxonomy/families", {}, "families", None, id="families-empty"
            ),
            pytest.param(
                "/api/detections/taxonomy/genera",
                {"family": "UnknownFamily"},
                "genera",
                "UnknownFamily",
                id="genera-unknown",
            ),
            pytest.param(
                "/api/detections/taxonomy/species",
                {"genus": "UnknownGenus"},
                "species",
                "UnknownGenus",
                id="species-unknown",
            ),
        ],
    )
    def test_get_taxonomy_empty_results(self, client, endpoint, params, field, filter_value):
        """Should handle empty results for taxonomy queries."""
        # Return data that doesn't match the filter
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"}
            ]
            if filter_value
            else [],
        )

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{endpoint}?{query_string}" if query_string else endpoint

        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data[field] == []
        assert data["count"] == 0

        # Check filter values are preserved in response
        if "family" in params:
            assert data["family"] == params["family"]
        if "genus" in params:
            assert data["genus"] == params["genus"]

    def test_get_families_without_detection_filter(self, client):
        """Should handle has_detections=false parameter."""
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"}
            ],
        )
        response = client.get("/api/detections/taxonomy/families?has_detections=false")
        assert response.status_code == 200
        data = response.json()
        assert "families" in data

    def test_get_genera_without_detection_filter(self, client):
        """Should handle has_detections=false parameter for genera."""
        client.mock_query_service.get_species_summary = AsyncMock(
            spec=DetectionQueryService.get_species_summary,
            return_value=[
                {"family": "Corvidae", "genus": "Corvus", "scientific_name": "Corvus corax"}
            ],
        )
        response = client.get(
            "/api/detections/taxonomy/genera?family=Corvidae&has_detections=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert "genera" in data
        assert data["family"] == "Corvidae"
