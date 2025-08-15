"""Tests for the DataManager - single source of truth for detection data access."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.managers.data_manager import DataManager
from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_query_service import (
    DetectionQueryService,
    DetectionWithLocalization,
)
from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.services.species_display_service import SpeciesDisplayService
from birdnetpi.web.models.detection import DetectionEvent


@pytest.fixture
def mock_services():
    """Create mock services for DataManager."""
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_multilingual = MagicMock(spec=MultilingualDatabaseService)
    mock_species_display = MagicMock(spec=SpeciesDisplayService)
    mock_query_service = MagicMock(spec=DetectionQueryService)

    return {
        "database_service": mock_db_service,
        "multilingual_service": mock_multilingual,
        "species_display_service": mock_species_display,
        "detection_query_service": mock_query_service,
    }


@pytest.fixture
def data_manager(mock_services):
    """Create a DataManager instance with mocked services."""
    return DataManager(
        database_service=mock_services["database_service"],
        multilingual_service=mock_services["multilingual_service"],
        species_display_service=mock_services["species_display_service"],
        detection_query_service=mock_services["detection_query_service"],
    )


class TestCoreOperations:
    """Test core CRUD operations."""

    def test_get_detection_by_id(self, data_manager, mock_services):
        """Should retrieve a detection by its ID."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_detection

        result = data_manager.get_detection_by_id(1)

        assert result == mock_detection
        mock_session.query.assert_called_once_with(Detection)

    def test_get_all_detections_with_pagination(self, data_manager, mock_services):
        """Should retrieve all detections with pagination."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
        mock_query = mock_session.query.return_value
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_detections

        result = data_manager.get_all_detections(limit=10, offset=20)

        assert result == mock_detections
        mock_query.offset.assert_called_once_with(20)
        mock_query.limit.assert_called_once_with(10)

    def test_create_detection(self, data_manager, mock_services):
        """Should create a new detection with audio file."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_file_path="/path/to/audio.wav",
            duration=10.0,
            size_bytes=1024,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )

        data_manager.create_detection(detection_event)

        # Verify AudioFile creation
        audio_file_call = mock_session.add.call_args_list[0]
        assert isinstance(audio_file_call[0][0], AudioFile)

        # Verify Detection creation
        detection_call = mock_session.add.call_args_list[1]
        assert isinstance(detection_call[0][0], Detection)

        mock_session.commit.assert_called_once()

    def test_update_detection(self, data_manager, mock_services):
        """Should update a detection record."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_detection.confidence = 0.8
        mock_session.query.return_value.filter.return_value.first.return_value = mock_detection

        updates = {"confidence": 0.95, "common_name": "Updated Robin"}
        result = data_manager.update_detection(1, updates)

        assert result == mock_detection
        assert mock_detection.confidence == 0.95
        assert mock_detection.common_name == "Updated Robin"
        mock_session.commit.assert_called_once()

    def test_delete_detection(self, data_manager, mock_services):
        """Should delete a detection record."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_detection

        result = data_manager.delete_detection(1)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_detection)
        mock_session.commit.assert_called_once()


class TestQueryMethods:
    """Test query methods."""

    def test_query_detections_with_filters(self, data_manager, mock_services):
        """Should query detections with multiple filters."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_query = mock_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_detections = [MagicMock(spec=Detection)]
        mock_query.all.return_value = mock_detections

        result = data_manager.query_detections(
            species="Turdus migratorius",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            min_confidence=0.8,
            limit=10,
            order_by="confidence",
            order_desc=True,
        )

        assert result == mock_detections
        assert mock_query.filter.called
        assert mock_query.order_by.called

    def test_query_detections_with_localization(self, data_manager, mock_services):
        """Should use DetectionQueryService when localization requested."""
        mock_detections = [MagicMock(spec=DetectionWithLocalization)]
        mock_services[
            "detection_query_service"
        ].get_detections_with_localization.return_value = mock_detections

        result = data_manager.query_detections(
            species="Turdus migratorius",
            include_localization=True,
            language_code="es",
        )

        assert result == mock_detections
        mock_services[
            "detection_query_service"
        ].get_detections_with_localization.assert_called_once()

    def test_get_detections_with_localization(self, data_manager, mock_services):
        """Should get detections with localized names."""
        mock_detections = [MagicMock(spec=DetectionWithLocalization)]
        mock_services[
            "detection_query_service"
        ].get_detections_with_localization.return_value = mock_detections

        filters = {"species": "Turdus migratorius", "family": "Turdidae"}
        result = data_manager.get_detections_with_localization(
            filters=filters,
            limit=50,
            language_code="fr",
        )

        assert result == mock_detections
        mock_services[
            "detection_query_service"
        ].get_detections_with_localization.assert_called_once()


class TestCountMethods:
    """Test count methods."""

    def test_count_detections(self, data_manager, mock_services):
        """Should count detections with filters."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_query = mock_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 42

        filters = {"species": "Turdus migratorius", "min_confidence": 0.8}
        result = data_manager.count_detections(filters)

        assert result == 42
        assert mock_query.filter.called

    def test_count_by_species(self, data_manager, mock_services):
        """Should count detections by species."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_query = mock_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [
            ("Turdus migratorius", 10),
            ("Cardinalis cardinalis", 5),
        ]

        result = data_manager.count_by_species(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )

        assert result == {"Turdus migratorius": 10, "Cardinalis cardinalis": 5}

    def test_count_by_date(self, data_manager, mock_services):
        """Should count detections by date."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        from datetime import date

        mock_query = mock_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [
            (date(2023, 1, 1), 5),
            (date(2023, 1, 2), 8),
        ]

        result = data_manager.count_by_date(species="Turdus migratorius")

        assert result == {date(2023, 1, 1): 5, date(2023, 1, 2): 8}


class TestTranslationHelpers:
    """Test translation helper methods."""

    def test_get_species_display_name_with_localization(self, data_manager, mock_services):
        """Should use species display service for DetectionWithLocalization."""
        mock_detection = MagicMock(spec=DetectionWithLocalization)
        mock_services[
            "species_display_service"
        ].format_species_display.return_value = "Merle d'Amérique"

        result = data_manager.get_species_display_name(
            mock_detection,
            prefer_translation=True,
            language_code="fr",
        )

        assert result == "Merle d'Amérique"
        mock_services["species_display_service"].format_species_display.assert_called_once_with(
            mock_detection, True
        )

    def test_get_species_display_name_plain_detection(self, data_manager, mock_services):
        """Should handle plain Detection objects."""
        mock_detection = MagicMock(spec=Detection)
        mock_detection.scientific_name = "Turdus migratorius"
        mock_detection.common_name = "American Robin"

        result = data_manager.get_species_display_name(
            mock_detection,
            prefer_translation=True,
        )

        assert result == "American Robin"


class TestSpecializedQueries:
    """Test specialized queries migrated from DetectionManager."""

    def test_get_recent_detections(self, data_manager, mock_services):
        """Should get recent detections using query_detections."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_query = mock_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_detections = [MagicMock(spec=Detection)]
        mock_query.all.return_value = mock_detections

        result = data_manager.get_recent_detections(limit=5)

        assert result == mock_detections
        mock_query.limit.assert_called_with(5)

    def test_get_top_species_with_prior_counts(self, data_manager, mock_services):
        """Should get top species with prior period counts."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        # Mock the complex query result
        mock_session.query().outerjoin().order_by().limit().all.return_value = [
            ("Turdus migratorius", "American Robin", 25, 15),
            ("Cardinalis cardinalis", "Northern Cardinal", 20, 10),
        ]

        result = data_manager.get_top_species_with_prior_counts(
            datetime(2023, 1, 1),
            datetime(2023, 1, 31),
            datetime(2022, 12, 1),
            datetime(2022, 12, 31),
        )

        assert len(result) == 2
        assert result[0]["scientific_name"] == "Turdus migratorius"
        assert result[0]["current_count"] == 25
        assert result[0]["prior_count"] == 15

    def test_get_best_detections(self, data_manager, mock_services):
        """Should get best detection per species by confidence."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        # Mock the complex window function query
        mock_subquery = MagicMock()
        mock_subquery.c.id = "id"
        mock_session.query.return_value.subquery.return_value = mock_subquery

        mock_detection = MagicMock(spec=Detection)
        mock_detection.scientific_name = "Turdus migratorius"
        mock_detection.confidence = 0.95

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_detection]

        # Set up the second query call - properly handle *args
        def query_side_effect(*args, **kwargs):
            if args and args[0] == Detection:
                return mock_query
            return MagicMock()

        mock_session.query.side_effect = query_side_effect

        result = data_manager.get_best_detections(limit=5)

        assert len(result) == 1
        assert result[0] == mock_detection


class TestErrorHandling:
    """Test error handling."""

    def test_database_error_handling(self, data_manager, mock_services):
        """Should handle database errors gracefully."""
        mock_session = MagicMock()
        mock_services["database_service"].get_db.return_value.__enter__.return_value = mock_session

        mock_session.query.side_effect = SQLAlchemyError("Database error")

        with pytest.raises(SQLAlchemyError):
            data_manager.get_detection_by_id(1)

        mock_session.rollback.assert_called_once()

    def test_no_query_service_for_localization(self, data_manager, mock_services):
        """Should raise error when query service not available for localization."""
        data_manager.query_service = None

        with pytest.raises(RuntimeError, match="DetectionQueryService not available"):
            data_manager.get_detections_with_localization()
