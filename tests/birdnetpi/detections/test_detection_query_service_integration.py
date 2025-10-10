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


class TestFirstDetectionFlags:
    """Tests for first detection identification with window functions."""

    @pytest.mark.asyncio
    async def test_first_ever_detection_across_all_time(self, query_service_with_db):
        """Should correctly identify the first ever detection of each species."""
        # Query all detections with first detection flags
        detections = await query_service_with_db.query_detections(
            include_first_detections=True, order_by="timestamp", order_desc=False
        )

        # Group detections by species
        species_detections = {}
        for detection in detections:
            species = detection.scientific_name
            if species not in species_detections:
                species_detections[species] = []
            species_detections[species].append(detection)

        # Verify each species has exactly one detection marked as first_ever
        for species, species_dets in species_detections.items():
            first_ever_count = sum(1 for d in species_dets if d.is_first_ever)
            assert first_ever_count == 1, (
                f"{species} should have exactly 1 first_ever detection, found {first_ever_count}"
            )

            # The first_ever flag should be on the earliest detection
            sorted_dets = sorted(species_dets, key=lambda d: d.timestamp)
            assert sorted_dets[0].is_first_ever, (
                f"Earliest detection of {species} should be marked as first_ever"
            )

    @pytest.mark.asyncio
    async def test_first_in_period_with_date_filter(self, query_service_with_db):
        """Should correctly identify first detection within a filtered time period."""
        # Filter to Jan 1, 2024 only
        start_date = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_date = datetime.datetime(2024, 1, 1, 23, 59, 59)

        detections = await query_service_with_db.query_detections(
            start_date=start_date,
            end_date=end_date,
            include_first_detections=True,
            order_by="timestamp",
            order_desc=False,
        )

        # Group by species
        species_detections = {}
        for detection in detections:
            species = detection.scientific_name
            if species not in species_detections:
                species_detections[species] = []
            species_detections[species].append(detection)

        # Each species should have exactly one detection marked as first_in_period
        for species, species_dets in species_detections.items():
            first_in_period_count = sum(1 for d in species_dets if d.is_first_in_period)
            assert first_in_period_count == 1, (
                f"{species} should have exactly 1 first_in_period detection on Jan 1, "
                f"found {first_in_period_count}"
            )

            # The first_in_period flag should be on the earliest detection in the period
            sorted_dets = sorted(species_dets, key=lambda d: d.timestamp)
            assert sorted_dets[0].is_first_in_period, (
                f"Earliest detection of {species} on Jan 1 should be marked as first_in_period"
            )

    @pytest.mark.asyncio
    async def test_first_ever_vs_first_in_period(self, query_service_with_db):
        """Should distinguish between first_ever and first_in_period correctly."""
        # American Robin has a detection on Dec 31, 2023 and multiple on Jan 1, 2024
        # Filter to Jan 1, 2024 only
        start_date = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_date = datetime.datetime(2024, 1, 1, 23, 59, 59)

        detections = await query_service_with_db.query_detections(
            species="Turdus migratorius",
            start_date=start_date,
            end_date=end_date,
            include_first_detections=True,
            order_by="timestamp",
            order_desc=False,
        )

        # Should have 3 detections of American Robin on Jan 1
        assert len(detections) == 3

        # NONE of them should be first_ever (because Dec 31 detection is earlier)
        first_ever_count = sum(1 for d in detections if d.is_first_ever)
        assert first_ever_count == 0, "No Jan 1 detections should be first_ever (Dec 31 is earlier)"

        # Exactly ONE should be first_in_period (the earliest on Jan 1)
        first_in_period_count = sum(1 for d in detections if d.is_first_in_period)
        assert first_in_period_count == 1, "Exactly one should be first_in_period for Jan 1"

        # The 06:15 detection should be first_in_period
        earliest_detection = min(detections, key=lambda d: d.timestamp)
        assert earliest_detection.is_first_in_period, (
            "Earliest Jan 1 detection should be first_in_period"
        )
        assert not earliest_detection.is_first_ever, (
            "Jan 1 detection should NOT be first_ever (Dec 31 is earlier)"
        )

    @pytest.mark.asyncio
    async def test_first_detection_with_confidence_filter(self, query_service_with_db):
        """Should calculate first detections correctly even with confidence filters."""
        # Query with high confidence filter
        detections = await query_service_with_db.query_detections(
            min_confidence=0.9,
            include_first_detections=True,
            order_by="timestamp",
            order_desc=False,
        )

        # Even with confidence filter, is_first_ever should reflect the global first
        # detection across ALL detections (not just high-confidence ones)
        for detection in detections:
            if detection.is_first_ever:
                # Verify this is actually the first detection of this species globally
                all_species_detections = await query_service_with_db.query_detections(
                    species=detection.scientific_name, order_by="timestamp", order_desc=False
                )
                first_global = all_species_detections[0]
                assert detection.timestamp == first_global.timestamp, (
                    "is_first_ever should match global first, not just filtered first"
                )

    @pytest.mark.asyncio
    async def test_first_detection_timestamps_populated(self, query_service_with_db):
        """Should populate first_ever_detection and first_period_detection timestamps."""
        start_date = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_date = datetime.datetime(2024, 1, 1, 23, 59, 59)

        detections = await query_service_with_db.query_detections(
            start_date=start_date,
            end_date=end_date,
            include_first_detections=True,
        )

        for detection in detections:
            # All detections should have first_ever_detection timestamp
            assert detection.first_ever_detection is not None, (
                f"Detection {detection.id} should have first_ever_detection timestamp"
            )

            # All detections should have first_period_detection timestamp
            assert detection.first_period_detection is not None, (
                f"Detection {detection.id} should have first_period_detection timestamp"
            )

            # first_period_detection should be >= start_date (within the filtered period)
            assert detection.first_period_detection >= start_date, (
                "first_period_detection should be within the filtered period"
            )

            # first_ever_detection should be <= first_period_detection
            # (global timestamp can't be after period-specific timestamp)
            assert detection.first_ever_detection <= detection.first_period_detection, (
                "first_ever_detection should be before or equal to first_period_detection"
            )

    @pytest.mark.asyncio
    async def test_species_with_single_detection(self, query_service_with_db):
        """Should handle species with only one detection correctly."""
        # Poecile carolinensis (Carolina Chickadee) only has one detection in the test data
        detections = await query_service_with_db.query_detections(
            species="Poecile carolinensis", include_first_detections=True
        )

        assert len(detections) == 1
        detection = detections[0]

        # For a species with only one detection, both flags should be True
        assert detection.is_first_ever, "Single detection should be first_ever"
        assert detection.is_first_in_period, "Single detection should be first_in_period"

        # Timestamps should all match
        assert detection.first_ever_detection == detection.timestamp
        assert detection.first_period_detection == detection.timestamp

    @pytest.mark.asyncio
    async def test_first_detection_with_family_filter(self, query_service_with_db):
        """Should calculate first detections correctly even with taxonomy filters."""
        # Filter by a family (this is a data filter, not a time filter)
        # The global ranking should still be across ALL detections
        detections = await query_service_with_db.query_detections(
            family="Turdidae",  # This is a data filter
            include_first_detections=True,
            order_by="timestamp",
            order_desc=False,
        )

        # Each species in the family should have is_first_ever flag on earliest detection
        species_detections = {}
        for detection in detections:
            species = detection.scientific_name
            if species not in species_detections:
                species_detections[species] = []
            species_detections[species].append(detection)

        for species, species_dets in species_detections.items():
            first_ever_count = sum(1 for d in species_dets if d.is_first_ever)
            assert first_ever_count <= 1, (
                f"{species} should have at most 1 first_ever detection in family filter"
            )

    @pytest.mark.asyncio
    async def test_first_detection_without_flag_returns_no_metadata(self, query_service_with_db):
        """Should not include first detection metadata when include_first_detections=False."""
        detections = await query_service_with_db.query_detections(include_first_detections=False)

        # These fields should be None when not requested
        for detection in detections:
            # The flags should be None/False (not populated)
            assert detection.is_first_ever is None or not detection.is_first_ever
            assert detection.is_first_in_period is None or not detection.is_first_in_period

            # The timestamp fields should also be None
            assert detection.first_ever_detection is None
            assert detection.first_period_detection is None
