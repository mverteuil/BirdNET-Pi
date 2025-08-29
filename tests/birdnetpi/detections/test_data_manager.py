"""Tests for the DataManager - single source of truth for detection data access."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import (
    DetectionQueryService,
)
from birdnetpi.detections.models import AudioFile, Detection, DetectionWithLocalization
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.web.models.detections import DetectionEvent


@pytest.fixture
def mock_services():
    """Create mock services for DataManager."""
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_multilingual = MagicMock(spec=MultilingualDatabaseService)
    mock_species_display = MagicMock(spec=SpeciesDisplayService)
    mock_query_service = MagicMock(spec=DetectionQueryService)
    mock_file_manager = MagicMock()
    mock_path_resolver = MagicMock()

    return {
        "database_service": mock_db_service,
        "multilingual_service": mock_multilingual,
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
        multilingual_service=mock_services["multilingual_service"],
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


class TestQueryMethods:
    """Test query methods."""

    @pytest.mark.asyncio
    async def test_query_detections_with_filters(self, data_manager, mock_services):
        """Should delegate query detections to DetectionQueryService."""
        mock_detections = [MagicMock(spec=Detection)]
        mock_services["detection_query_service"].query_detections = AsyncMock(
            return_value=mock_detections
        )

        result = await data_manager.query_detections(
            species="Turdus migratorius",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            min_confidence=0.8,
            limit=10,
            order_by="confidence",
            order_desc=True,
        )

        assert result == mock_detections
        mock_services["detection_query_service"].query_detections.assert_called_once_with(
            species="Turdus migratorius",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            min_confidence=0.8,
            max_confidence=None,
            limit=10,
            offset=None,
            order_by="confidence",
            order_desc=True,
            include_localization=False,
            language_code="en",
        )

    @pytest.mark.asyncio
    async def test_query_detections_with_localization(self, data_manager, mock_services):
        """Should use DetectionQueryService when localization requested."""
        mock_detections = [MagicMock(spec=DetectionWithLocalization)]
        mock_services["detection_query_service"].query_detections = AsyncMock(
            return_value=mock_detections
        )

        result = await data_manager.query_detections(
            species="Turdus migratorius",
            include_localization=True,
            language_code="es",
        )

        assert result == mock_detections
        mock_services["detection_query_service"].query_detections.assert_called_once()


class TestCountMethods:
    """Test count methods."""

    @pytest.mark.asyncio
    async def test_count_detections(self, data_manager, mock_services):
        """Should count detections with filters."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        mock_session.scalar.return_value = 42

        filters = {"species": "Turdus migratorius", "min_confidence": 0.8}
        result = await data_manager.count_detections(filters)

        assert result == 42
        assert mock_session.scalar.called

    @pytest.mark.asyncio
    async def test_count_by_species(self, data_manager, mock_services):
        """Should count detections by species."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        # Return Row-like objects with dictionary access
        mock_row1 = MagicMock()
        mock_row1.__getitem__ = lambda self, key: {
            "scientific_name": "Turdus migratorius",
            "count": 10,
        }[key]
        mock_row2 = MagicMock()
        mock_row2.__getitem__ = lambda self, key: {
            "scientific_name": "Cardinalis cardinalis",
            "count": 5,
        }[key]
        mock_session.execute.return_value.__iter__ = lambda self: iter([mock_row1, mock_row2])

        result = await data_manager.count_by_species(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )

        assert result == {"Turdus migratorius": 10, "Cardinalis cardinalis": 5}

    @pytest.mark.asyncio
    async def test_count_by_date(self, data_manager, mock_services):
        """Should count detections by date."""
        mock_session = AsyncMock()
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        from datetime import date

        # Return Row-like objects with dictionary access
        mock_row1 = MagicMock()
        mock_row1.__getitem__ = lambda self, key: {"date": date(2023, 1, 1), "count": 5}[key]
        mock_row2 = MagicMock()
        mock_row2.__getitem__ = lambda self, key: {"date": date(2023, 1, 2), "count": 8}[key]
        mock_session.execute.return_value.__iter__ = lambda self: iter([mock_row1, mock_row2])

        result = await data_manager.count_by_date(species="Turdus migratorius")

        assert result == {date(2023, 1, 1): 5, date(2023, 1, 2): 8}


class TestTranslationHelpers:
    """Test translation helper methods."""

    @pytest.mark.asyncio
    async def test_get_species_display_name_with_localization(self, data_manager, mock_services):
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

    @pytest.mark.asyncio
    async def test_get_species_display_name_plain_detection(self, data_manager, mock_services):
        """Should handle plain Detection objects."""
        mock_detection = MagicMock(spec=Detection)
        mock_detection.scientific_name = "Turdus migratorius"
        mock_detection.common_name = "American Robin"

        result = data_manager.get_species_display_name(
            mock_detection,
            prefer_translation=True,
        )

        assert result == "American Robin"


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


class TestAnalyticsMethods:
    """Test analytics-specific methods added for AnalyticsManager integration."""

    @pytest.mark.asyncio
    async def test_get_detection_count(self, data_manager, mock_services):
        """Should return count of detections in time range."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 23, 59, 59)

        # Mock the database session with scalar method
        mock_session = AsyncMock()
        # session.scalar() returns the count directly
        mock_session.scalar = AsyncMock(return_value=42)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        count = await data_manager.get_detection_count(start_time, end_time)

        assert count == 42
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unique_species_count(self, data_manager, mock_services):
        """Should return count of unique species in time range."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 23, 59, 59)

        # Mock the database session with scalar method
        mock_session = AsyncMock()
        # session.scalar() returns the count directly
        mock_session.scalar = AsyncMock(return_value=15)
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        count = await data_manager.get_unique_species_count(start_time, end_time)

        assert count == 15
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_storage_metrics(self, data_manager, mock_services):
        """Should return storage metrics for audio files."""
        # Mock the database session and query result
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.total_bytes = 1024 * 1024 * 100  # 100MB
        mock_row.total_duration = 3600  # 1 hour
        mock_result.first.return_value = mock_row
        mock_session.execute.return_value = mock_result
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        metrics = await data_manager.get_storage_metrics()

        assert metrics["total_bytes"] == 1024 * 1024 * 100
        assert metrics["total_duration"] == 3600
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_storage_metrics_no_data(self, data_manager, mock_services):
        """Should return zeros when no audio files exist."""
        # Mock the database session with no results
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        metrics = await data_manager.get_storage_metrics()

        assert metrics["total_bytes"] == 0
        assert metrics["total_duration"] == 0

    @pytest.mark.asyncio
    async def test_get_species_counts(self, data_manager, mock_services):
        """Should return species with detection counts."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 23, 59, 59)

        # Mock the database session and query result
        mock_session = AsyncMock()
        mock_result = MagicMock()

        # Create mock rows
        mock_row1 = MagicMock()
        mock_row1.scientific_name = "Turdus migratorius"
        mock_row1.common_name = "American Robin"
        mock_row1.count = 25

        mock_row2 = MagicMock()
        mock_row2.scientific_name = "Cardinalis cardinalis"
        mock_row2.common_name = "Northern Cardinal"
        mock_row2.count = 18

        mock_result.__iter__ = MagicMock(return_value=iter([mock_row1, mock_row2]))
        mock_session.execute.return_value = mock_result
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        species_counts = await data_manager.get_species_counts(start_time, end_time)

        assert len(species_counts) == 2
        assert species_counts[0]["scientific_name"] == "Turdus migratorius"
        assert species_counts[0]["common_name"] == "American Robin"
        assert species_counts[0]["count"] == 25
        assert species_counts[1]["scientific_name"] == "Cardinalis cardinalis"
        assert species_counts[1]["common_name"] == "Northern Cardinal"
        assert species_counts[1]["count"] == 18

    @pytest.mark.asyncio
    async def test_get_hourly_counts(self, data_manager, mock_services):
        """Should return hourly detection counts for a date."""
        from datetime import date

        target_date = date(2024, 1, 1)

        # Mock the database session and query result
        mock_session = AsyncMock()
        mock_result = MagicMock()

        # Create mock rows for different hours
        mock_row1 = MagicMock()
        mock_row1.hour = "06"
        mock_row1.count = 10

        mock_row2 = MagicMock()
        mock_row2.hour = "07"
        mock_row2.count = 15

        mock_row3 = MagicMock()
        mock_row3.hour = "08"
        mock_row3.count = 20

        mock_result.__iter__ = MagicMock(return_value=iter([mock_row1, mock_row2, mock_row3]))
        mock_session.execute.return_value = mock_result
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        hourly_counts = await data_manager.get_hourly_counts(target_date)

        assert len(hourly_counts) == 3
        assert hourly_counts[0]["hour"] == 6
        assert hourly_counts[0]["count"] == 10
        assert hourly_counts[1]["hour"] == 7
        assert hourly_counts[1]["count"] == 15
        assert hourly_counts[2]["hour"] == 8
        assert hourly_counts[2]["count"] == 20

    @pytest.mark.asyncio
    async def test_analytics_methods_handle_errors(self, data_manager, mock_services):
        """Should handle database errors gracefully in analytics methods."""
        from datetime import date

        # Mock the database session to raise an error
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("Database error")
        mock_session.scalar.side_effect = SQLAlchemyError("Database error")
        mock_session.rollback = AsyncMock()  # Mock rollback method
        mock_services[
            "database_service"
        ].get_async_db.return_value.__aenter__.return_value = mock_session

        # Test each method handles errors and raises them
        with pytest.raises(SQLAlchemyError):
            await data_manager.get_detection_count(datetime.now(), datetime.now())

        with pytest.raises(SQLAlchemyError):
            await data_manager.get_unique_species_count(datetime.now(), datetime.now())

        with pytest.raises(SQLAlchemyError):
            await data_manager.get_storage_metrics()

        with pytest.raises(SQLAlchemyError):
            await data_manager.get_species_counts(datetime.now(), datetime.now())

        with pytest.raises(SQLAlchemyError):
            await data_manager.get_hourly_counts(date.today())
