"""Integration tests for DetectionQueryService with real database."""

import datetime
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_species_database():
    """Create a mock SpeciesDatabaseService."""
    mock_service = MagicMock(spec=SpeciesDatabaseService)
    return mock_service


@pytest.fixture
async def test_database(tmp_path):
    """Should create a test database with DatabaseService."""
    db_path = tmp_path / "test.db"
    db_service = CoreDatabaseService(db_path)
    await db_service.initialize()
    try:
        yield db_service
    finally:
        await db_service.dispose()


@pytest.fixture
async def populated_database(test_database, model_factory):
    """Create a test database with sample data."""
    async with test_database.get_async_db() as session:
        # Create audio files using factory
        audio_files = model_factory.create_audio_files(9, duration=3.0, size_bytes=48000)
        for i, audio in enumerate(audio_files):
            audio.file_path = Path(f"/recordings/detection_{i + 1}.wav")

        session.add_all(audio_files)
        await session.flush()
        audio_file_ids = [af.id for af in audio_files]

        # Define detection data (timestamp, species_data, confidence, week)
        detection_data = [
            (
                datetime.datetime(2024, 1, 1, 6, 15, 0),
                ("Turdus migratorius", "American Robin"),
                0.95,
                1,
            ),
            (
                datetime.datetime(2024, 1, 1, 6, 30, 0),
                ("Turdus migratorius", "American Robin"),
                0.88,
                1,
            ),
            (
                datetime.datetime(2024, 1, 1, 6, 45, 0),
                ("Cardinalis cardinalis", "Northern Cardinal"),
                0.92,
                1,
            ),
            (
                datetime.datetime(2024, 1, 1, 7, 10, 0),
                ("Cardinalis cardinalis", "Northern Cardinal"),
                0.85,
                1,
            ),
            (datetime.datetime(2024, 1, 1, 7, 20, 0), ("Cyanocitta cristata", "Blue Jay"), 0.9, 1),
            (
                datetime.datetime(2024, 1, 1, 7, 40, 0),
                ("Turdus migratorius", "American Robin"),
                0.91,
                1,
            ),
            (datetime.datetime(2024, 1, 1, 8, 5, 0), ("Cyanocitta cristata", "Blue Jay"), 0.87, 1),
            (
                datetime.datetime(2024, 1, 1, 8, 25, 0),
                ("Poecile carolinensis", "Carolina Chickadee"),
                0.93,
                1,
            ),
            (
                datetime.datetime(2023, 12, 31, 10, 0, 0),
                ("Turdus migratorius", "American Robin"),
                0.89,
                52,
            ),
        ]

        # Create detections using factory with common defaults
        detections = []
        for i, (timestamp, (scientific, common), confidence, week) in enumerate(detection_data):
            detection = model_factory.create_detection(
                audio_file_id=audio_file_ids[i],
                timestamp=timestamp,
                species_tensor=f"{scientific}_{common}",
                scientific_name=scientific,
                common_name=common,
                confidence=confidence,
                species_confidence_threshold=0.5,
                week=week,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            detections.append(detection)

        session.add_all(detections)
        await session.commit()
    return test_database


@pytest.fixture
async def query_service_with_db(populated_database, path_resolver, test_config):
    """Create DetectionQueryService with real populated database."""
    species_database = SpeciesDatabaseService(path_resolver)
    return DetectionQueryService(
        core_database=populated_database, species_database=species_database, config=test_config
    )


class TestAnalyticsIntegration:
    """Integration tests for analytics methods with real database."""

    @pytest.mark.asyncio
    async def test_get_detection_count(self, query_service_with_db):
        """Should counting detections in time range."""
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)
        count = await query_service_with_db.get_detection_count(start_time, end_time)
        assert count == 8
        morning_start = datetime.datetime(2024, 1, 1, 6, 0, 0)
        morning_end = datetime.datetime(2024, 1, 1, 6, 59, 59)
        morning_count = await query_service_with_db.get_detection_count(morning_start, morning_end)
        assert morning_count == 3
        prev_day_start = datetime.datetime(2023, 12, 31, 0, 0, 0)
        prev_day_end = datetime.datetime(2023, 12, 31, 23, 59, 59)
        prev_count = await query_service_with_db.get_detection_count(prev_day_start, prev_day_end)
        assert prev_count == 1

    @pytest.mark.asyncio
    async def test_get_unique_species_count(self, query_service_with_db):
        """Should counting unique species in time range."""
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)
        species_count = await query_service_with_db.get_unique_species_count(start_time, end_time)
        assert species_count == 4
        morning_start = datetime.datetime(2024, 1, 1, 6, 0, 0)
        morning_end = datetime.datetime(2024, 1, 1, 6, 59, 59)
        morning_species = await query_service_with_db.get_unique_species_count(
            morning_start, morning_end
        )
        assert morning_species == 2

    @pytest.mark.asyncio
    async def test_get_storage_metrics(self, query_service_with_db):
        """Should getting storage metrics for audio files."""
        metrics = await query_service_with_db.get_storage_metrics()
        expected_bytes = 9 * 48000
        assert metrics["total_bytes"] == expected_bytes
        expected_duration = 9 * 3.0
        assert metrics["total_duration"] == expected_duration

    @pytest.mark.asyncio
    async def test_get_species_counts(self, query_service_with_db):
        """Should getting species with their detection counts."""
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)
        species_counts = await query_service_with_db.get_species_counts(start_time, end_time)
        assert len(species_counts) == 4
        species_dict = {s["scientific_name"]: s for s in species_counts}
        assert species_dict["Turdus migratorius"]["count"] == 3
        assert species_dict["Cardinalis cardinalis"]["count"] == 2
        assert species_dict["Cyanocitta cristata"]["count"] == 2
        assert species_dict["Poecile carolinensis"]["count"] == 1
        assert species_dict["Turdus migratorius"]["common_name"] == "American Robin"
        assert species_dict["Cardinalis cardinalis"]["common_name"] == "Northern Cardinal"

    @pytest.mark.asyncio
    async def test_get_hourly_counts(self, query_service_with_db):
        """Should getting hourly detection counts for a date."""
        target_date = date(2024, 1, 1)
        hourly_counts = await query_service_with_db.get_hourly_counts(target_date)
        hourly_dict = {h["hour"]: h["count"] for h in hourly_counts}
        assert hourly_dict.get(6, 0) == 3
        assert hourly_dict.get(7, 0) == 3
        assert hourly_dict.get(8, 0) == 2
        assert hourly_dict.get(9, 0) == 0
        assert hourly_dict.get(12, 0) == 0
        assert hourly_dict.get(18, 0) == 0

    @pytest.mark.asyncio
    async def test_empty_database_queries(self, test_database, mock_species_database, test_config):
        """Should handle analytics methods correctly with empty database."""
        query_service = DetectionQueryService(
            core_database=test_database, species_database=mock_species_database, config=test_config
        )
        start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2024, 1, 1, 23, 59, 59)
        assert await query_service.get_detection_count(start_time, end_time) == 0
        assert await query_service.get_unique_species_count(start_time, end_time) == 0
        metrics = await query_service.get_storage_metrics()
        assert metrics["total_bytes"] == 0
        assert metrics["total_duration"] == 0
        assert await query_service.get_species_counts(start_time, end_time) == []
        assert await query_service.get_hourly_counts(date(2024, 1, 1)) == []

    @pytest.mark.asyncio
    async def test_query_best_recordings_with_species_filter(self, query_service_with_db):
        """Should return all recordings for a specific species without per-species limit."""
        detections, total = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=None,
            min_confidence=0.5,
            page=1,
            per_page=10,
            species="Turdus migratorius",
        )
        assert total == 4
        assert len(detections) == 4
        for detection in detections:
            assert detection.detection.scientific_name == "Turdus migratorius"
        confidences = [d.detection.confidence for d in detections]
        assert confidences == sorted(confidences, reverse=True)

    @pytest.mark.asyncio
    async def test_query_best_recordings_without_species_filter(self, query_service_with_db):
        """Should return limited recordings per species when no species filter."""
        detections, _ = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=2, min_confidence=0.5, page=1, per_page=10
        )
        species_counts = {}
        for detection in detections:
            species = detection.detection.scientific_name
            species_counts[species] = species_counts.get(species, 0) + 1
        for species, count in species_counts.items():
            assert count <= 2, f"{species} has {count} recordings, expected <= 2"
        assert species_counts.get("Turdus migratorius", 0) <= 2

    @pytest.mark.asyncio
    async def test_query_best_recordings_with_family_filter(self, query_service_with_db):
        """Should filter recordings by family correctly."""
        detections, total = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=5, min_confidence=0.5, page=1, per_page=10, family="Turdidae"
        )
        assert isinstance(detections, list)
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_query_best_recordings_with_confidence_filter(self, query_service_with_db):
        """Should filter recordings by minimum confidence threshold."""
        detections, _ = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=5, min_confidence=0.8, page=1, per_page=10
        )
        for detection in detections:
            assert detection.detection.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_query_best_recordings_pagination(self, query_service_with_db):
        """Should paginate best recordings correctly."""
        page1, total1 = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=2, min_confidence=0.5, page=1, per_page=3
        )
        page2, total2 = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=2, min_confidence=0.5, page=2, per_page=3
        )
        assert total1 == total2
        assert len(page1) <= 3
        page1_ids = {d.detection.id for d in page1}
        page2_ids = {d.detection.id for d in page2}
        assert len(page1_ids & page2_ids) == 0

    @pytest.mark.asyncio
    async def test_query_best_recordings_none_limit_without_species(self, query_service_with_db):
        """Should handle None per_species_limit without species filter."""
        detections, _ = await query_service_with_db.query_best_recordings_per_species(
            per_species_limit=None, min_confidence=0.5, page=1, per_page=20
        )
        assert len(detections) <= 9
