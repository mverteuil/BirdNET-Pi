"""Tests for the DataManager - single source of truth for detection data access."""

import base64
from datetime import datetime
from unittest.mock import MagicMock, create_autospec

import pytest
from sqlalchemy.engine import ScalarResult
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager


@pytest.fixture
def mock_services(path_resolver, db_service_factory):
    """Create mock services for DataManager."""
    mock_db_service, _session, _result = db_service_factory()
    mock_multilingual = MagicMock(spec=SpeciesDatabaseService)
    mock_species_display = MagicMock(spec=SpeciesDisplayService)
    mock_query_service = MagicMock(spec=DetectionQueryService)
    mock_file_manager = MagicMock(spec=FileManager)
    return {
        "database_service": mock_db_service,
        "species_database": mock_multilingual,
        "species_display_service": mock_species_display,
        "detection_query_service": mock_query_service,
        "file_manager": mock_file_manager,
        "path_resolver": path_resolver,
    }


@pytest.fixture
def data_manager(mock_services):
    """Create a DataManager instance with mocked services."""
    return DataManager(
        database_service=mock_services["database_service"],
        species_database=mock_services["species_database"],
        species_display_service=mock_services["species_display_service"],
        detection_query_service=mock_services["detection_query_service"],
        file_manager=mock_services["file_manager"],
        path_resolver=mock_services["path_resolver"],
    )


class TestCoreOperations:
    """Test core CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_detection_by_id(self, data_manager, mock_services, db_service_factory):
        """Should retrieve a detection by its ID."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_detection = MagicMock(spec=Detection)
        result.scalar_one_or_none.return_value = mock_detection
        result_value = await data_manager.get_detection_by_id(1)
        assert result_value == mock_detection
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_pagination(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should retrieve all detections with pagination."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
        mock_scalars = create_autospec(ScalarResult, spec_set=True)
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        result.scalars.return_value = mock_scalars
        result_value = await data_manager.get_all_detections(limit=10, offset=20)
        assert list(result_value) == mock_detections
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection(
        self, data_manager, mock_services, detection_event_factory, db_service_factory
    ):
        """Should create a new detection with audio file."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        test_audio_bytes = b"test audio data"
        encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")
        detection_event = detection_event_factory(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data=encoded_audio,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        await data_manager.create_detection(detection_event)
        audio_file_call = session.add.call_args_list[0]
        assert isinstance(audio_file_call[0][0], AudioFile)
        detection_call = session.add.call_args_list[1]
        assert isinstance(detection_call[0][0], Detection)
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_detection(self, data_manager, mock_services, db_service_factory):
        """Should update a detection record."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_detection = MagicMock(spec=Detection)
        mock_detection.confidence = 0.8
        result.scalar_one_or_none.return_value = mock_detection
        updates = {"confidence": 0.95, "common_name": "Updated Robin"}
        result_value = await data_manager.update_detection(1, updates)
        assert result_value == mock_detection
        assert mock_detection.confidence == 0.95
        assert mock_detection.common_name == "Updated Robin"
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_detection(self, data_manager, mock_services, db_service_factory):
        """Should delete a detection record."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_detection = MagicMock(spec=Detection)
        result.scalar_one_or_none.return_value = mock_detection
        result_value = await data_manager.delete_detection(1)
        assert result_value is True
        session.delete.assert_called_once_with(mock_detection)
        session.commit.assert_called_once()


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_database_error_handling(self, data_manager, mock_services, db_service_factory):
        """Should handle database errors gracefully."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.execute.side_effect = SQLAlchemyError("Database error")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_detection_by_id(1)
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_detections_error_handling(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should handle errors when getting all detections."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.execute.side_effect = SQLAlchemyError("Database error")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_all_detections()
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection_error_handling(
        self, data_manager, mock_services, detection_event_factory, db_service_factory
    ):
        """Should handle errors during detection creation."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.commit.side_effect = SQLAlchemyError("Commit failed")
        test_audio_bytes = b"test audio data"
        encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")
        detection_event = detection_event_factory(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data=encoded_audio,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        with pytest.raises(SQLAlchemyError):
            await data_manager.create_detection(detection_event)
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_detection_error_handling(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should handle errors during detection update."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.execute.side_effect = SQLAlchemyError("Update failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.update_detection(1, {"confidence": 0.99})
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_detection_error_handling(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should handle errors during detection deletion."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.execute.side_effect = SQLAlchemyError("Delete failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.delete_detection(1)
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_file_error_handling(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should handle errors when getting audio file."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.scalar.side_effect = SQLAlchemyError("Query failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_audio_file_by_path("/path/to/audio.wav")
        session.rollback.assert_called_once()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_update_detection_not_found(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should return None when updating non-existent detection."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        result.scalar_one_or_none.return_value = None
        result_value = await data_manager.update_detection(999, {"confidence": 0.99})
        assert result_value is None
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_detection_not_found(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should return False when deleting non-existent detection."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        result.scalar_one_or_none.return_value = None
        result_value = await data_manager.delete_detection(999)
        assert result_value is False
        session.delete.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_offset_no_limit(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should handle offset without limit."""
        mock_db_service, session, result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_detections = [MagicMock(spec=Detection)]
        mock_scalars = create_autospec(ScalarResult, spec_set=True)
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        result.scalars.return_value = mock_scalars
        result_value = await data_manager.get_all_detections(offset=50)
        assert list(result_value) == mock_detections
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection_without_audio(
        self, data_manager, mock_services, detection_event_factory, db_service_factory
    ):
        """Should create detection without audio data."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        detection_event = detection_event_factory(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data="",
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        await data_manager.create_detection(detection_event)
        assert session.add.call_count == 1
        detection_call = session.add.call_args_list[0]
        assert isinstance(detection_call[0][0], Detection)
        assert detection_call[0][0].audio_file_id is None
        session.commit.assert_called_once()


class TestAudioFileOperations:
    """Test AudioFile-related operations."""

    @pytest.mark.asyncio
    async def test_get_audio_file_by_path_success(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should retrieve audio file by path."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        mock_audio_file = MagicMock(spec=AudioFile)
        session.scalar.return_value = mock_audio_file
        result_value = await data_manager.get_audio_file_by_path("/path/to/audio.wav")
        assert result_value == mock_audio_file
        session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_file_by_path_not_found(
        self, data_manager, mock_services, db_service_factory
    ):
        """Should return None when audio file not found."""
        mock_db_service, session, _result = db_service_factory()
        mock_services["database_service"].get_async_db = mock_db_service.get_async_db
        session.scalar.return_value = None
        result_value = await data_manager.get_audio_file_by_path("/nonexistent/audio.wav")
        assert result_value is None
        session.scalar.assert_called_once()
