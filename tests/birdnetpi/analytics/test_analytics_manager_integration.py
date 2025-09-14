"""Integration tests for AnalyticsManager with real database."""

import datetime
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
async def test_database_with_data(tmp_path):
    """Should create a test database with sample data for analytics testing."""
    db_path = tmp_path / "test.db"
    db_service = CoreDatabaseService(db_path)

    # Initialize the database
    await db_service.initialize()

    # Create test data
    async with db_service.get_async_db() as session:
        # Create audio files and detections for different time periods
        # Use a fixed date/time for reproducible tests
        now = datetime.datetime(2024, 3, 15, 15, 30, 0)  # 3:30 PM on March 15, 2024
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Morning detections (today) - 3 hours ago
        for i in range(5):
            audio = AudioFile(
                file_path=Path(f"/recordings/morning_{i}.wav"), duration=3.0, size_bytes=48000
            )
            session.add(audio)
            await session.flush()

            detection = Detection(
                audio_file_id=audio.id,
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.85 + i * 0.02,
                timestamp=now - timedelta(hours=3) + timedelta(minutes=i * 10),
                species_confidence_threshold=0.5,
                week=1,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            session.add(detection)

        # Afternoon detections (today) - 2 hours ago
        for i in range(3):
            audio = AudioFile(
                file_path=Path(f"/recordings/afternoon_{i}.wav"), duration=3.0, size_bytes=48000
            )
            session.add(audio)
            await session.flush()

            detection = Detection(
                audio_file_id=audio.id,
                species_tensor="Cardinalis cardinalis_Northern Cardinal",
                scientific_name="Cardinalis cardinalis",
                common_name="Northern Cardinal",
                confidence=0.90 + i * 0.01,
                timestamp=now - timedelta(hours=2, minutes=-i * 15),
                species_confidence_threshold=0.5,
                week=1,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            session.add(detection)

        # Evening detection (today) - 1 hour ago
        audio = AudioFile(file_path=Path("/recordings/evening.wav"), duration=3.0, size_bytes=48000)
        session.add(audio)
        await session.flush()

        detection = Detection(
            audio_file_id=audio.id,
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.88,
            timestamp=now - timedelta(hours=1),
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        session.add(detection)

        # Debug: count today's detections
        await session.flush()
        from sqlalchemy import func, select

        # Debug timestamps
        all_detections = await session.scalars(select(Detection))
        for det in all_detections:
            is_today = det.timestamp >= today_start and det.timestamp < today_start + timedelta(
                days=1
            )
            print(
                f"DEBUG: Detection timestamp: {det.timestamp}, today_start: {today_start}, "
                f"is_today: {is_today}"
            )

        today_count_query = select(func.count(Detection.id)).where(
            Detection.timestamp >= today_start,
            Detection.timestamp < today_start + timedelta(days=1),
        )
        today_count = await session.scalar(today_count_query)
        print(f"DEBUG: Created {today_count} detections for today (expecting 9)")

        # Yesterday's detections
        yesterday = today_start - timedelta(days=1)
        for i in range(2):
            audio = AudioFile(
                file_path=Path(f"/recordings/yesterday_{i}.wav"), duration=3.0, size_bytes=48000
            )
            session.add(audio)
            await session.flush()

            detection = Detection(
                audio_file_id=audio.id,
                species_tensor="Poecile carolinensis_Carolina Chickadee",
                scientific_name="Poecile carolinensis",
                common_name="Carolina Chickadee",
                confidence=0.92,
                timestamp=yesterday + timedelta(hours=10, minutes=i * 30),
                species_confidence_threshold=0.5,
                week=1,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            session.add(detection)

        # Last week's detections
        last_week = today_start - timedelta(days=8)
        audio = AudioFile(
            file_path=Path("/recordings/last_week.wav"), duration=3.0, size_bytes=48000
        )
        session.add(audio)
        await session.flush()

        detection = Detection(
            audio_file_id=audio.id,
            species_tensor="Sitta carolinensis_White-breasted Nuthatch",
            scientific_name="Sitta carolinensis",
            common_name="White-breasted Nuthatch",
            confidence=0.85,
            timestamp=last_week + timedelta(hours=12),
            species_confidence_threshold=0.5,
            week=52,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        session.add(detection)

        await session.commit()

    try:
        # Return both db_service and the reference time
        yield (db_service, now)
    finally:
        # Properly dispose all database resources
        await db_service.dispose()


@pytest.fixture
def mock_species_database():
    """Create a mock SpeciesDatabaseService."""
    mock_service = MagicMock(spec=SpeciesDatabaseService)
    # Mock the async methods used during query execution
    mock_service.attach_all_to_session = AsyncMock()
    mock_service.detach_all_from_session = AsyncMock()
    return mock_service


@pytest.fixture
def mock_species_display_service():
    """Create a mock SpeciesDisplayService."""
    config = BirdNETConfig()
    return SpeciesDisplayService(config)


@pytest.fixture
def mock_detection_query_service(test_database_with_data, mock_species_database):
    """Create a DetectionQueryService with mocks."""
    db_service, _ = test_database_with_data  # Unpack tuple
    return DetectionQueryService(db_service, mock_species_database)


@pytest.fixture
async def analytics_manager_with_db(
    test_database_with_data,
    mock_species_database,
):
    """Create AnalyticsManager with real database."""
    db_service, _ = test_database_with_data  # Unpack tuple
    config = BirdNETConfig()
    config.species_confidence_threshold = 0.5

    detection_query_service = DetectionQueryService(
        core_database=db_service,
        species_database=mock_species_database,
    )

    return AnalyticsManager(detection_query_service, config)


class TestDashboardAnalyticsIntegration:
    """Integration tests for dashboard analytics."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary_integration(
        self, analytics_manager_with_db, test_database_with_data, mocker
    ):
        """Should generate dashboard summary with real data."""
        # Use the same fixed time reference that was used to create the test data
        _, fixed_now = test_database_with_data  # Unpack tuple

        # Patch datetime to use our fixed reference time
        mock_datetime = mocker.patch("birdnetpi.analytics.analytics.datetime")
        mock_datetime.now.return_value = fixed_now
        mock_datetime.min = datetime.datetime.min
        mocker.patch("birdnetpi.analytics.analytics.timedelta", datetime.timedelta)

        summary = await analytics_manager_with_db.get_dashboard_summary()

        # Debug: print actual values
        print(f"DEBUG: summary = {summary}")

        # Today: 5 Robin + 3 Cardinal + 1 Blue Jay = 9 detections
        assert summary["detections_today"] == 9

        # Total species: Robin, Cardinal, Blue Jay, Chickadee, Nuthatch = 5
        assert summary["species_total"] == 5

        # This week (last 7 days): Robin, Cardinal, Blue Jay, Chickadee = 4
        assert summary["species_week"] == 4

        # Storage: 12 files * 48000 bytes = 576000 bytes
        assert summary["storage_gb"] == pytest.approx(576000 / (1024**3), rel=1e-6)

        # Duration: 12 files * 3 seconds = 36 seconds
        assert summary["hours_monitored"] == pytest.approx(36 / 3600, rel=1e-6)

        assert summary["confidence_threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_integration(
        self, analytics_manager_with_db, test_database_with_data, mocker
    ):
        """Should analyze species frequency with real data."""
        # Use the same fixed time reference that was used to create the test data
        _, fixed_now = test_database_with_data  # Unpack tuple

        # Patch datetime to use our fixed reference time
        mock_datetime = mocker.patch("birdnetpi.analytics.analytics.datetime")
        mock_datetime.now.return_value = fixed_now
        mock_datetime.min = datetime.datetime.min
        mocker.patch("birdnetpi.analytics.analytics.timedelta", datetime.timedelta)

        # Analyze last 24 hours
        analysis = await analytics_manager_with_db.get_species_frequency_analysis(hours=24)

        # Should have today's species
        assert len(analysis) == 3

        # Find each species
        species_by_name = {s["name"]: s for s in analysis}

        # American Robin: 5 detections
        assert "American Robin" in species_by_name
        assert species_by_name["American Robin"]["count"] == 5
        assert species_by_name["American Robin"]["percentage"] == pytest.approx(5 / 9 * 100)
        assert species_by_name["American Robin"]["category"] == "uncommon"

        # Northern Cardinal: 3 detections
        assert "Northern Cardinal" in species_by_name
        assert species_by_name["Northern Cardinal"]["count"] == 3
        assert species_by_name["Northern Cardinal"]["percentage"] == pytest.approx(3 / 9 * 100)

        # Blue Jay: 1 detection
        assert "Blue Jay" in species_by_name
        assert species_by_name["Blue Jay"]["count"] == 1
        assert species_by_name["Blue Jay"]["percentage"] == pytest.approx(1 / 9 * 100)

    @pytest.mark.asyncio
    async def test_get_temporal_patterns_integration(
        self, analytics_manager_with_db, test_database_with_data, mocker
    ):
        """Should identify temporal patterns with real data."""
        # Use the same fixed time reference that was used to create the test data
        _, fixed_now = test_database_with_data  # Unpack tuple
        today = fixed_now.date()

        # Patch datetime to use our fixed reference time
        mock_datetime = mocker.patch("birdnetpi.analytics.analytics.datetime")
        mock_datetime.now.return_value = fixed_now
        mock_datetime.combine = datetime.datetime.combine
        mocker.patch("birdnetpi.analytics.analytics.timedelta", datetime.timedelta)

        patterns = await analytics_manager_with_db.get_temporal_patterns(today)

        # Check hourly distribution - detections spread across hours due to minute offsets
        hourly = patterns["hourly_distribution"]

        # Total should be 9 detections
        total_detections = sum(hourly)
        assert total_detections == 9

        # Should have detections in at least 3 different hours
        hours_with_detections = [h for h, count in enumerate(hourly) if count > 0]
        assert len(hours_with_detections) >= 3

        # Peak hour should have the most detections
        peak_hour = patterns["peak_hour"]
        assert peak_hour is not None
        assert hourly[peak_hour] == max(hourly)

        # Period aggregations - just check total is 9
        total_in_periods = sum(patterns["periods"].values())
        assert total_in_periods == 9  # All 9 detections should be accounted for

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_integration(
        self, analytics_manager_with_db, test_database_with_data, mocker
    ):
        """Should generate scatter plot data with real detections."""
        # Use the same fixed time reference that was used to create the test data
        _, fixed_now = test_database_with_data  # Unpack tuple

        # Patch datetime to use our fixed reference time
        mock_datetime = mocker.patch("birdnetpi.analytics.analytics.datetime")
        mock_datetime.now.return_value = fixed_now
        mocker.patch("birdnetpi.analytics.analytics.timedelta", datetime.timedelta)

        scatter_data = await analytics_manager_with_db.get_detection_scatter_data(hours=24)

        # Should have today's 9 detections
        assert len(scatter_data) == 9

        # Check time conversion for morning detections
        morning_times = [d["time"] for d in scatter_data if d["species"] == "American Robin"]
        assert len(morning_times) == 5

        # Times should be around (fixed_now - 3 hours)
        expected_hour = (fixed_now - timedelta(hours=3)).hour + (
            fixed_now - timedelta(hours=3)
        ).minute / 60
        # Allow for some variation in minutes
        assert min(morning_times) == pytest.approx(expected_hour, abs=1.0)

        # Check confidence values
        robin_confidences = [
            d["confidence"] for d in scatter_data if d["species"] == "American Robin"
        ]
        assert min(robin_confidences) == pytest.approx(0.85, rel=0.01)
        assert max(robin_confidences) == pytest.approx(0.93, rel=0.01)

        # Check frequency categories
        for detection in scatter_data:
            # All species have low counts, should be "uncommon"
            assert detection["frequency_category"] == "uncommon"

    @pytest.mark.asyncio
    async def test_get_species_frequency_analysis_multiple_days(
        self, analytics_manager_with_db, test_database_with_data, mocker
    ):
        """Should analyze species frequency across multiple days."""
        # Use the same fixed time reference that was used to create the test data
        _, fixed_now = test_database_with_data  # Unpack tuple

        # Patch datetime to use our fixed reference time
        mock_datetime = mocker.patch("birdnetpi.analytics.analytics.datetime")
        mock_datetime.now.return_value = fixed_now
        mock_datetime.min = datetime.datetime.min
        mocker.patch("birdnetpi.analytics.analytics.timedelta", datetime.timedelta)

        # Analyze last 48 hours (includes yesterday)
        analysis = await analytics_manager_with_db.get_species_frequency_analysis(hours=48)

        # Should include yesterday's Chickadee
        assert len(analysis) == 4

        species_names = [s["name"] for s in analysis]
        assert "Carolina Chickadee" in species_names

        # Find Chickadee
        chickadee = next(s for s in analysis if s["name"] == "Carolina Chickadee")
        assert chickadee["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_time_range(self, analytics_manager_with_db):
        """Should analytics with a time range that has no data."""
        # Get data for a future date
        future_date = date.today() + timedelta(days=30)
        patterns = await analytics_manager_with_db.get_temporal_patterns(future_date)

        # Should have all zeros
        assert all(count == 0 for count in patterns["hourly_distribution"])
        # Peak hour defaults to 6 AM (typical bird activity time) when no data
        assert patterns["peak_hour"] == 6
        assert all(patterns["periods"][period] == 0 for period in patterns["periods"])
