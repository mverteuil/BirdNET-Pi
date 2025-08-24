"""Integration tests for DataManager analytics methods with real database."""

import datetime
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import DetectionQueryService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
def mock_multilingual_service():
    """Create a mock MultilingualDatabaseService."""
    mock_service = MagicMock(spec=MultilingualDatabaseService)
    # Configure any needed mock behaviors
    return mock_service


@pytest.fixture
def mock_species_display_service():
    """Create a mock SpeciesDisplayService."""
    config = BirdNETConfig()
    return SpeciesDisplayService(config)


@pytest.fixture
def mock_detection_query_service(test_database, mock_multilingual_service):
    """Create a DetectionQueryService with mocks."""
    return DetectionQueryService(test_database, mock_multilingual_service)


@pytest.fixture
async def test_database(tmp_path):
    """Create a test database with DatabaseService."""
    db_path = tmp_path / "test.db"
    db_service = DatabaseService(db_path)

    # Initialize the database
    await db_service.initialize()

    try:
        yield db_service
    finally:
        # Close async engine to prevent event loop warnings
        if hasattr(db_service, "async_engine"):
            await db_service.async_engine.dispose()


@pytest.fixture
async def populated_database(test_database):
    """Create a test database with sample data."""
    # Create test audio files
    async with test_database.get_async_db() as session:
        # Create audio files - one for each detection
        audio_files = []
        for i in range(9):  # 9 detections total
            audio = AudioFile(
                file_path=Path(f"/recordings/detection_{i + 1}.wav"),
                duration=3.0,  # 3 second clips
                size_bytes=48000,  # ~48KB per 3-second clip
            )
            audio_files.append(audio)

        session.add_all(audio_files)
        await session.flush()  # Flush to get IDs

        # Get the IDs while in the async context
        audio_file_ids = [af.id for af in audio_files]

        # Create detections at different times for different species
        # Morning detections (6 AM)
        detection1 = Detection(
            audio_file_id=audio_file_ids[0],
            timestamp=datetime.datetime(2024, 1, 1, 6, 15, 0),
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        detection2 = Detection(
            audio_file_id=audio_file_ids[1],
            timestamp=datetime.datetime(2024, 1, 1, 6, 30, 0),
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.88,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        detection3 = Detection(
            audio_file_id=audio_file_ids[2],
            timestamp=datetime.datetime(2024, 1, 1, 6, 45, 0),
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            confidence=0.92,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )

        # 7 AM detections
        detection4 = Detection(
            audio_file_id=audio_file_ids[3],
            timestamp=datetime.datetime(2024, 1, 1, 7, 10, 0),
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            confidence=0.85,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        detection5 = Detection(
            audio_file_id=audio_file_ids[4],
            timestamp=datetime.datetime(2024, 1, 1, 7, 20, 0),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.90,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        detection6 = Detection(
            audio_file_id=audio_file_ids[5],
            timestamp=datetime.datetime(2024, 1, 1, 7, 40, 0),
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.91,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )

        # 8 AM detections
        detection7 = Detection(
            audio_file_id=audio_file_ids[6],
            timestamp=datetime.datetime(2024, 1, 1, 8, 5, 0),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.87,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        detection8 = Detection(
            audio_file_id=audio_file_ids[7],
            timestamp=datetime.datetime(2024, 1, 1, 8, 25, 0),
            species_tensor="Poecile carolinensis_Carolina Chickadee",
            scientific_name="Poecile carolinensis",
            common_name="Carolina Chickadee",
            confidence=0.93,
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )

        # Add a detection from previous day for testing date filtering
        detection9 = Detection(
            audio_file_id=audio_file_ids[8],
            timestamp=datetime.datetime(2023, 12, 31, 10, 0, 0),
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.89,
            species_confidence_threshold=0.5,
            week=52,
            sensitivity_setting=1.0,
            overlap=0.0,
        )

        session.add_all(
            [
                detection1,
                detection2,
                detection3,
                detection4,
                detection5,
                detection6,
                detection7,
                detection8,
                detection9,
            ]
        )
        await session.commit()

    return test_database


@pytest.fixture
async def data_manager_with_db(populated_database, mocker):
    """Create DataManager with real populated database."""
    # Mock the other services that DataManager needs
    mock_multilingual = mocker.MagicMock(spec=MultilingualDatabaseService)
    mock_species_display = mocker.MagicMock(spec=SpeciesDisplayService)
    mock_query_service = mocker.MagicMock(spec=DetectionQueryService)

    return DataManager(
        database_service=populated_database,
        multilingual_service=mock_multilingual,
        species_display_service=mock_species_display,
        detection_query_service=mock_query_service,
    )


class TestAnalyticsIntegration:
    """Integration tests for analytics methods with real database."""

    @pytest.mark.asyncio
    async def test_get_detection_count(self, data_manager_with_db):
        """Test counting detections in time range."""
        # Count all detections on Jan 1, 2024
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)

        count = await data_manager_with_db.get_detection_count(start_time, end_time)
        assert count == 8  # 8 detections on Jan 1

        # Count detections in morning only (6-7 AM)
        morning_start = datetime.datetime(2024, 1, 1, 6, 0, 0)
        morning_end = datetime.datetime(2024, 1, 1, 6, 59, 59)

        morning_count = await data_manager_with_db.get_detection_count(morning_start, morning_end)
        assert morning_count == 3  # 3 detections in 6 AM hour

        # Count detections on Dec 31, 2023
        prev_day_start = datetime.datetime(2023, 12, 31, 0, 0, 0)
        prev_day_end = datetime.datetime(2023, 12, 31, 23, 59, 59)

        prev_count = await data_manager_with_db.get_detection_count(prev_day_start, prev_day_end)
        assert prev_count == 1  # 1 detection on Dec 31

    @pytest.mark.asyncio
    async def test_get_unique_species_count(self, data_manager_with_db):
        """Test counting unique species in time range."""
        # Count unique species on Jan 1, 2024
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)

        species_count = await data_manager_with_db.get_unique_species_count(start_time, end_time)
        assert species_count == 4  # American Robin, Northern Cardinal, Blue Jay, Carolina Chickadee

        # Count unique species in morning only
        morning_start = datetime.datetime(2024, 1, 1, 6, 0, 0)
        morning_end = datetime.datetime(2024, 1, 1, 6, 59, 59)

        morning_species = await data_manager_with_db.get_unique_species_count(
            morning_start, morning_end
        )
        assert morning_species == 2  # American Robin, Northern Cardinal

    @pytest.mark.asyncio
    async def test_get_storage_metrics(self, data_manager_with_db):
        """Test getting storage metrics for audio files."""
        metrics = await data_manager_with_db.get_storage_metrics()

        # Total size: 9 files * 48000 bytes = 432000 bytes
        expected_bytes = 9 * 48000
        assert metrics["total_bytes"] == expected_bytes

        # Total duration: 9 files * 3 seconds = 27 seconds
        expected_duration = 9 * 3.0
        assert metrics["total_duration"] == expected_duration

    @pytest.mark.asyncio
    async def test_get_species_counts(self, data_manager_with_db):
        """Test getting species with their detection counts."""
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)

        species_counts = await data_manager_with_db.get_species_counts(start_time, end_time)

        # Should be sorted by count descending
        assert len(species_counts) == 4

        # Find each species in the results
        species_dict = {s["scientific_name"]: s for s in species_counts}

        assert species_dict["Turdus migratorius"]["count"] == 3  # American Robin
        assert species_dict["Cardinalis cardinalis"]["count"] == 2  # Northern Cardinal
        assert species_dict["Cyanocitta cristata"]["count"] == 2  # Blue Jay
        assert species_dict["Poecile carolinensis"]["count"] == 1  # Carolina Chickadee

        # Verify the common names are included
        assert species_dict["Turdus migratorius"]["common_name"] == "American Robin"
        assert species_dict["Cardinalis cardinalis"]["common_name"] == "Northern Cardinal"

    @pytest.mark.asyncio
    async def test_get_hourly_counts(self, data_manager_with_db):
        """Test getting hourly detection counts for a date."""
        target_date = date(2024, 1, 1)

        hourly_counts = await data_manager_with_db.get_hourly_counts(target_date)

        # Convert to dict for easier testing
        hourly_dict = {h["hour"]: h["count"] for h in hourly_counts}

        # Verify counts for hours with detections
        assert hourly_dict.get(6, 0) == 3  # 3 detections at 6 AM
        assert hourly_dict.get(7, 0) == 3  # 3 detections at 7 AM
        assert hourly_dict.get(8, 0) == 2  # 2 detections at 8 AM

        # Verify other hours have no detections (may not be in result)
        assert hourly_dict.get(9, 0) == 0
        assert hourly_dict.get(12, 0) == 0
        assert hourly_dict.get(18, 0) == 0

    @pytest.mark.asyncio
    async def test_get_detections_in_range(self, data_manager_with_db):
        """Test getting all detections within a time range."""
        # Get all detections on Jan 1, 2024
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)

        detections = await data_manager_with_db.get_detections_in_range(start_time, end_time)

        assert len(detections) == 8

        # All detections should be within the time range
        for detection in detections:
            assert detection.timestamp >= start_time
            assert detection.timestamp <= end_time

        # Test narrower time range
        morning_start = datetime.datetime(2024, 1, 1, 7, 0, 0)
        morning_end = datetime.datetime(2024, 1, 1, 7, 59, 59)

        morning_detections = await data_manager_with_db.get_detections_in_range(
            morning_start, morning_end
        )
        assert len(morning_detections) == 3

        # Check species in morning detections
        morning_species = {d.scientific_name for d in morning_detections}
        assert "Cardinalis cardinalis" in morning_species
        assert "Cyanocitta cristata" in morning_species
        assert "Turdus migratorius" in morning_species

    @pytest.mark.asyncio
    async def test_empty_database_queries(
        self,
        test_database,
        mock_multilingual_service,
        mock_species_display_service,
        mock_detection_query_service,
    ):
        """Test analytics methods with empty database."""
        # Create DataManager with empty database
        data_manager = DataManager(
            database_service=test_database,
            multilingual_service=mock_multilingual_service,
            species_display_service=mock_species_display_service,
            detection_query_service=mock_detection_query_service,
        )

        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)

        # All methods should return appropriate empty values
        assert await data_manager.get_detection_count(start_time, end_time) == 0
        assert await data_manager.get_unique_species_count(start_time, end_time) == 0

        metrics = await data_manager.get_storage_metrics()
        assert metrics["total_bytes"] == 0
        assert metrics["total_duration"] == 0

        assert await data_manager.get_species_counts(start_time, end_time) == []
        assert await data_manager.get_hourly_counts(date(2024, 1, 1)) == []
        assert await data_manager.get_detections_in_range(start_time, end_time) == []
