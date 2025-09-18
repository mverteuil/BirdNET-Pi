"""Tests for the DataManager - single source of truth for detection data access."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.detections.queries import (
    DetectionQueryService,
)
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.web.models.detections import DetectionEvent


@pytest.fixture
def mock_services():
    """Create mock services for DataManager."""
    mock_db_service = MagicMock(spec=CoreDatabaseService)
    mock_multilingual = MagicMock(spec=SpeciesDatabaseService)
    mock_species_display = MagicMock(spec=SpeciesDisplayService)
    mock_query_service = MagicMock(spec=DetectionQueryService)
    mock_file_manager = MagicMock()
    mock_path_resolver = MagicMock()

    return {
        "database_service": mock_db_service,
        "species_database": mock_multilingual,
        "species_display_service": mock_species_display,
        "detection_query_service": mock_query_service,
        "file_manager": mock_file_manager,
        "path_resolver": mock_path_resolver,
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
        mock_session = MagicMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await data_manager.get_detection_by_id(1)

        assert result == mock_detection
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_pagination(self, data_manager, mock_services):
        """Should retrieve all detections with pagination."""
        mock_session = MagicMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await data_manager.get_all_detections(limit=10, offset=20)

        assert list(result) == mock_detections
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection(self, data_manager, mock_services):
        """Should create a new detection with audio file."""
        mock_session = AsyncMock()
        # Configure synchronous methods on AsyncSession
        mock_session.add = MagicMock()  # add() is synchronous even in AsyncSession
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        # Create valid base64-encoded audio data (just a few bytes for testing)
        import base64

        test_audio_bytes = b"test audio data"
        encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")

        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data=encoded_audio,  # Valid base64-encoded audio
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

        # Verify AudioFile creation
        audio_file_call = mock_session.add.call_args_list[0]
        assert isinstance(audio_file_call[0][0], AudioFile)

        # Verify Detection creation
        detection_call = mock_session.add.call_args_list[1]
        assert isinstance(detection_call[0][0], Detection)

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_detection(self, data_manager, mock_services):
        """Should update a detection record."""
        mock_session = MagicMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_detection.confidence = 0.8
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        updates = {"confidence": 0.95, "common_name": "Updated Robin"}
        result = await data_manager.update_detection(1, updates)

        assert result == mock_detection
        assert mock_detection.confidence == 0.95
        assert mock_detection.common_name == "Updated Robin"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_detection(self, data_manager, mock_services):
        """Should delete a detection record."""
        mock_session = MagicMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_detection = MagicMock(spec=Detection)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = MagicMock()
        mock_session.commit = AsyncMock()

        result = await data_manager.delete_detection(1)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_detection)
        mock_session.commit.assert_called_once()


# TestQueryMethods removed - query_detections now belongs to DetectionQueryService
# See test_detection_query_service.py for tests of these methods


# TestTranslationHelpers removed - get_species_display_name now belongs to DetectionQueryService
# See test_detection_query_service.py for tests of these methods


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_database_error_handling(self, data_manager, mock_services):
        """Should handle database errors gracefully."""
        mock_session = AsyncMock()
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
        mock_session = AsyncMock()
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
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        # Make commit fail
        mock_session.commit.side_effect = SQLAlchemyError("Commit failed")

        import base64

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
        mock_session = AsyncMock()
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
        mock_session = AsyncMock()
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
        mock_session = AsyncMock()
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
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Detection not found
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await data_manager.update_detection(999, {"confidence": 0.99})

        assert result is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_detection_not_found(self, data_manager, mock_services):
        """Should return False when deleting non-existent detection."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Detection not found
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await data_manager.delete_detection(999)

        assert result is False
        mock_session.delete.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_detections_with_offset_no_limit(self, data_manager, mock_services):
        """Should handle offset without limit."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_detections = [MagicMock(spec=Detection)]
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = lambda x: iter(mock_detections)
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await data_manager.get_all_detections(offset=50)

        assert list(result) == mock_detections
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_detection_without_audio(self, data_manager, mock_services):
        """Should create detection without audio data."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        detection_event = DetectionEvent(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            audio_data="",  # Empty string instead of None
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

        # Should only add Detection, not AudioFile
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
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_audio_file = MagicMock(spec=AudioFile)
        mock_session.scalar = AsyncMock(return_value=mock_audio_file)

        result = await data_manager.get_audio_file_by_path("/path/to/audio.wav")

        assert result == mock_audio_file
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_file_by_path_not_found(self, data_manager, mock_services):
        """Should return None when audio file not found."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_session.scalar = AsyncMock(return_value=None)

        result = await data_manager.get_audio_file_by_path("/nonexistent/audio.wav")

        assert result is None
        mock_session.scalar.assert_called_once()


# TestAnalyticsMethods removed - these methods now belong to DetectionQueryService
# See test_detection_query_service.py for tests of these methods
