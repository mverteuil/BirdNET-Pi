"""Tests for the DataManager - single source of truth for detection data access."""

import base64
from datetime import datetime
from unittest.mock import MagicMock, create_autospec

import pytest
from sqlalchemy.engine import Result, ScalarResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.web.models.detections import DetectionEvent


@pytest.fixture
def mock_services(path_resolver):
    """Create mock services for DataManager."""
    mock_db_service = MagicMock(spec=CoreDatabaseService)
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
    async def test_get_detection_by_id(self, data_manager, mock_services):
        """Should retrieve a detection by its ID."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_detection = MagicMock(spec=Detection)
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute.return_value = mock_result
        result = await data_manager.get_detection_by_id(1)
        assert result == mock_detection
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_pagination(self, data_manager, mock_services):
        """Should retrieve all detections with pagination."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
        mock_scalars = create_autospec(ScalarResult, spec_set=True)
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        result = await data_manager.get_all_detections(limit=10, offset=20)
        assert list(result) == mock_detections
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection(self, data_manager, mock_services):
        """Should create a new detection with audio file."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        test_audio_bytes = b"test audio data"
        encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")
        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data=encoded_audio,
            sample_rate=48000,
            channels=1,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        await data_manager.create_detection(detection_event)
        audio_file_call = mock_session.add.call_args_list[0]
        assert isinstance(audio_file_call[0][0], AudioFile)
        detection_call = mock_session.add.call_args_list[1]
        assert isinstance(detection_call[0][0], Detection)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_detection(self, data_manager, mock_services):
        """Should update a detection record."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_detection = MagicMock(spec=Detection)
        mock_detection.confidence = 0.8
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute.return_value = mock_result
        updates = {"confidence": 0.95, "common_name": "Updated Robin"}
        result = await data_manager.update_detection(1, updates)
        assert result == mock_detection
        assert mock_detection.confidence == 0.95
        assert mock_detection.common_name == "Updated Robin"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_detection(self, data_manager, mock_services):
        """Should delete a detection record."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_detection = MagicMock(spec=Detection)
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute.return_value = mock_result
        result = await data_manager.delete_detection(1)
        assert result is True
        mock_session.delete.assert_called_once_with(mock_detection)
        mock_session.commit.assert_called_once()


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_database_error_handling(self, data_manager, mock_services):
        """Should handle database errors gracefully."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.execute.side_effect = SQLAlchemyError("Database error")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_detection_by_id(1)
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_detections_error_handling(self, data_manager, mock_services):
        """Should handle errors when getting all detections."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.execute.side_effect = SQLAlchemyError("Database error")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_all_detections()
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection_error_handling(self, data_manager, mock_services):
        """Should handle errors during detection creation."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.commit.side_effect = SQLAlchemyError("Commit failed")
        test_audio_bytes = b"test audio data"
        encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")
        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data=encoded_audio,
            sample_rate=48000,
            channels=1,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        with pytest.raises(SQLAlchemyError):
            await data_manager.create_detection(detection_event)
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_detection_error_handling(self, data_manager, mock_services):
        """Should handle errors during detection update."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.execute.side_effect = SQLAlchemyError("Update failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.update_detection(1, {"confidence": 0.99})
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_detection_error_handling(self, data_manager, mock_services):
        """Should handle errors during detection deletion."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.execute.side_effect = SQLAlchemyError("Delete failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.delete_detection(1)
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_file_error_handling(self, data_manager, mock_services):
        """Should handle errors when getting audio file."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.scalar.side_effect = SQLAlchemyError("Query failed")
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_audio_file_by_path("/path/to/audio.wav")
        mock_session.rollback.assert_called_once()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_update_detection_not_found(self, data_manager, mock_services):
        """Should return None when updating non-existent detection."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await data_manager.update_detection(999, {"confidence": 0.99})
        assert result is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_detection_not_found(self, data_manager, mock_services):
        """Should return False when deleting non-existent detection."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await data_manager.delete_detection(999)
        assert result is False
        mock_session.delete.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_offset_no_limit(self, data_manager, mock_services):
        """Should handle offset without limit."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_detections = [MagicMock(spec=Detection)]
        mock_scalars = create_autospec(ScalarResult, spec_set=True)
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        mock_result = create_autospec(Result, spec_set=True)
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        result = await data_manager.get_all_detections(offset=50)
        assert list(result) == mock_detections
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection_without_audio(self, data_manager, mock_services):
        """Should create detection without audio data."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data="",
            sample_rate=48000,
            channels=1,
            latitude=45.5017,
            longitude=-73.5673,
            species_confidence_threshold=0.8,
            week=1,
            sensitivity_setting=1.5,
            overlap=2.5,
        )
        await data_manager.create_detection(detection_event)
        assert mock_session.add.call_count == 1
        detection_call = mock_session.add.call_args_list[0]
        assert isinstance(detection_call[0][0], Detection)
        assert detection_call[0][0].audio_file_id is None
        mock_session.commit.assert_called_once()


class TestAudioFileOperations:
    """Test AudioFile-related operations."""

    @pytest.mark.asyncio
    async def test_get_audio_file_by_path_success(self, data_manager, mock_services):
        """Should retrieve audio file by path."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_audio_file = MagicMock(spec=AudioFile)
        mock_session.scalar.return_value = mock_audio_file
        result = await data_manager.get_audio_file_by_path("/path/to/audio.wav")
        assert result == mock_audio_file
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_file_by_path_not_found(self, data_manager, mock_services):
        """Should return None when audio file not found."""
        mock_session = create_autospec(AsyncSession, spec_set=True, instance=True)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session
        mock_session.scalar.return_value = None
        result = await data_manager.get_audio_file_by_path("/nonexistent/audio.wav")
        assert result is None
        mock_session.scalar.assert_called_once()
