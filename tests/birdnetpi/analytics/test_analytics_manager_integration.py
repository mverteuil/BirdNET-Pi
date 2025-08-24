"""Integration tests for AnalyticsManager with real database."""

import datetime
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import DetectionQueryService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
async def test_database_with_data(tmp_path):
    """Create a test database with sample data for analytics testing."""
    db_path = tmp_path / "test.db"
    db_service = DatabaseService(db_path)

    # Initialize the database
    await db_service.initialize()

    # Create test data
    async with db_service.get_async_db() as session:
        # Create audio files and detections for different time periods
        now = datetime.datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Morning detections (today)
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
                timestamp=today_start + timedelta(hours=6, minutes=i * 10),
                species_confidence_threshold=0.5,
                week=1,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            session.add(detection)

        # Afternoon detections (today)
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
                timestamp=today_start + timedelta(hours=14, minutes=i * 15),
                species_confidence_threshold=0.5,
                week=1,
                sensitivity_setting=1.0,
                overlap=0.0,
            )
            session.add(detection)

        # Evening detection (today)
        audio = AudioFile(file_path=Path("/recordings/evening.wav"), duration=3.0, size_bytes=48000)
        session.add(audio)
        await session.flush()

        detection = Detection(
            audio_file_id=audio.id,
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.88,
            timestamp=today_start + timedelta(hours=18, minutes=30),
            species_confidence_threshold=0.5,
            week=1,
            sensitivity_setting=1.0,
            overlap=0.0,
        )
        session.add(detection)

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
        yield db_service
    finally:
        # Close async engine to prevent event loop warnings
        if hasattr(db_service, "async_engine"):
            await db_service.async_engine.dispose()


@pytest.fixture
def mock_multilingual_service():
    """Create a mock MultilingualDatabaseService."""
    mock_service = MagicMock(spec=MultilingualDatabaseService)
    return mock_service


@pytest.fixture
def mock_species_display_service():
    """Create a mock SpeciesDisplayService."""
    config = BirdNETConfig()
    return SpeciesDisplayService(config)


@pytest.fixture
def mock_detection_query_service(test_database_with_data, mock_multilingual_service):
    """Create a DetectionQueryService with mocks."""
    return DetectionQueryService(test_database_with_data, mock_multilingual_service)


@pytest.fixture
async def analytics_manager_with_db(
    test_database_with_data,
    mock_multilingual_service,
    mock_species_display_service,
    mock_detection_query_service,
):
    """Create AnalyticsManager with real database."""
    config = BirdNETConfig()
    config.species_confidence_threshold = 0.5

    data_manager = DataManager(
        database_service=test_database_with_data,
        multilingual_service=mock_multilingual_service,
        species_display_service=mock_species_display_service,
        detection_query_service=mock_detection_query_service,
    )

    return AnalyticsManager(data_manager, config)


class TestDashboardAnalyticsIntegration:
    """Integration tests for dashboard analytics."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary_integration(self, analytics_manager_with_db):
        """Test dashboard summary with real data."""
        summary = await analytics_manager_with_db.get_dashboard_summary()

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
    async def test_get_species_frequency_analysis_integration(self, analytics_manager_with_db):
        """Test species frequency analysis with real data."""
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
    async def test_get_temporal_patterns_integration(self, analytics_manager_with_db):
        """Test temporal patterns with real data."""
        today = datetime.datetime.now().date()
        patterns = await analytics_manager_with_db.get_temporal_patterns(today)

        # Check hourly distribution
        hourly = patterns["hourly_distribution"]

        # 6 AM: 5 detections (Robin)
        assert hourly[6] == 5

        # 14 (2 PM): 3 detections (Cardinal)
        assert hourly[14] == 3

        # 18 (6 PM): 1 detection (Blue Jay)
        assert hourly[18] == 1

        # Other hours should be 0
        assert hourly[0] == 0
        assert hourly[12] == 0
        assert hourly[23] == 0

        # Peak hour should be 6 AM
        assert patterns["peak_hour"] == 6

        # Period aggregations (6 equal 4-hour periods)
        assert patterns["periods"]["night_early"] == 0  # 12am-4am: no detections
        assert patterns["periods"]["dawn"] == 5  # 4am-8am: hour 6 has 5 detections
        assert patterns["periods"]["morning"] == 0  # 8am-12pm: no detections
        assert patterns["periods"]["afternoon"] == 3  # 12pm-4pm: hour 14 has 3 detections
        assert patterns["periods"]["evening"] == 1  # 4pm-8pm: hour 18 has 1 detection
        assert patterns["periods"]["night_late"] == 0  # 8pm-12am: no detections

    @pytest.mark.asyncio
    async def test_get_detection_scatter_data_integration(self, analytics_manager_with_db):
        """Test scatter plot data with real detections."""
        scatter_data = await analytics_manager_with_db.get_detection_scatter_data(hours=24)

        # Should have today's 9 detections
        assert len(scatter_data) == 9

        # Check time conversion for morning detections
        morning_times = [d["time"] for d in scatter_data if d["species"] == "American Robin"]
        assert len(morning_times) == 5

        # First morning detection at 6:00
        assert min(morning_times) == pytest.approx(6.0, rel=0.01)

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
    async def test_get_species_frequency_analysis_multiple_days(self, analytics_manager_with_db):
        """Test species frequency analysis across multiple days."""
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
        """Test analytics with a time range that has no data."""
        # Get data for a future date
        future_date = date.today() + timedelta(days=30)
        patterns = await analytics_manager_with_db.get_temporal_patterns(future_date)

        # Should have all zeros
        assert all(count == 0 for count in patterns["hourly_distribution"])
        assert patterns["peak_hour"] is None
        assert all(patterns["periods"][period] == 0 for period in patterns["periods"])
