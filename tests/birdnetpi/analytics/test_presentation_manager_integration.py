"""Integration tests for PresentationManager with real database."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
async def test_database_with_data(tmp_path):
    """Create a test database with sample data for presentation testing."""
    db_path = tmp_path / "test.db"
    db_service = CoreDatabaseService(db_path)

    # Initialize the database
    await db_service.initialize()

    # Add sample data
    async with db_service.get_async_db() as session:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Create detections with various species and confidence levels
        species_list = [
            ("Turdus migratorius", "American Robin"),
            ("Cardinalis cardinalis", "Northern Cardinal"),
            ("Cyanocitta cristata", "Blue Jay"),
            ("Poecile carolinensis", "Carolina Chickadee"),
            ("Sitta carolinensis", "White-breasted Nuthatch"),
        ]

        # Batch create all audio files and detections to minimize DB operations
        audio_files = []
        detections = []

        # Create 15 detections spread across today (reduced from 40 but maintains test coverage)
        for i in range(15):
            # Spread across different times of day for temporal patterns
            hour = (i * 2) % 24  # Cover all hours with fewer samples
            minute = (i * 15) % 60
            timestamp = today_start.replace(hour=hour, minute=minute)

            # Create audio file
            audio_file = AudioFile(
                file_path=Path(f"/recordings/audio_{i}.wav"),
                duration=10.0,
                size_bytes=1024 * 1024,  # Simplified size
            )
            audio_files.append(audio_file)

        # Add all audio files in one batch
        session.add_all(audio_files)
        await session.flush()  # Single flush to get IDs

        # Create detections using the audio file IDs
        for i, audio_file in enumerate(audio_files):
            # Select species in rotation
            species_idx = i % len(species_list)
            scientific_name, common_name = species_list[species_idx]

            # Vary confidence levels
            confidence = 0.5 + ((i * 0.03) % 0.5)

            hour = (i * 2) % 24
            minute = (i * 15) % 60
            timestamp = today_start.replace(hour=hour, minute=minute)

            detection = Detection(
                audio_file_id=audio_file.id,
                species_tensor=f"{scientific_name}_{common_name}",
                scientific_name=scientific_name,
                common_name=common_name,
                confidence=confidence,
                timestamp=timestamp,
            )
            detections.append(detection)

        # Add 5 detections from the past week for weekly stats (reduced from 10)
        week_ago = now - timedelta(days=7)
        week_audio_files = []

        for i in range(5):
            audio_file = AudioFile(
                file_path=Path(f"/recordings/week_audio_{i}.wav"),
                duration=10.0,
                size_bytes=1024 * 1024,
            )
            week_audio_files.append(audio_file)

        session.add_all(week_audio_files)
        await session.flush()  # Single flush for week audio files

        for i, audio_file in enumerate(week_audio_files):
            timestamp = week_ago + timedelta(days=i % 7, hours=i * 4)
            species_idx = i % len(species_list)
            scientific_name, common_name = species_list[species_idx]

            detection = Detection(
                audio_file_id=audio_file.id,
                species_tensor=f"{scientific_name}_{common_name}",
                scientific_name=scientific_name,
                common_name=common_name,
                confidence=0.7 + (i * 0.02),
                timestamp=timestamp,
            )
            detections.append(detection)

        # Add all detections in one batch
        session.add_all(detections)
        await session.commit()  # Single commit for all data

    try:
        yield db_service
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
    return DetectionQueryService(test_database_with_data, mock_species_database)


@pytest.fixture
async def presentation_manager(
    test_database_with_data,
    mock_species_database,
):
    """Create PresentationManager with real components."""
    db_service = test_database_with_data

    # Create real components
    config = BirdNETConfig()
    config.species_confidence_threshold = 0.5

    # Create DetectionQueryService
    detection_query_service = DetectionQueryService(
        core_database=db_service,
        species_database=mock_species_database,
    )

    # Create AnalyticsManager with DetectionQueryService
    analytics_manager = AnalyticsManager(detection_query_service, config)

    return PresentationManager(analytics_manager, detection_query_service, config)


class TestLandingPageIntegration:
    """Test landing page data with real database."""

    @pytest.mark.asyncio
    @patch("birdnetpi.analytics.presentation.SystemInspector")
    @patch("time.time")
    async def test_get_landing_page_data_integration(
        self, mock_time, mock_inspector, presentation_manager
    ):
        """Test complete landing page data retrieval with real data."""
        # Configure system mocks
        mock_time.return_value = 1704240000.0  # Fixed time for testing

        # Only need to mock get_system_info since that's what the code calls
        mock_inspector.get_system_info.return_value = {
            "boot_time": 1704067200.0,  # 2 days ago
            "cpu_percent": 45.5,
            "cpu_temperature": 55.0,
            "memory": {
                "percent": 60.0,
                "used": 4 * 1024**3,  # 4GB
                "total": 8 * 1024**3,  # 8GB
            },
            "disk": {
                "percent": 75.0,
                "used": 75 * 1024**3,  # 75GB
                "total": 100 * 1024**3,  # 100GB
            },
            "device_name": "Test Device",
        }

        # Get landing page data
        data = await presentation_manager.get_landing_page_data()

        # Verify structure (Pydantic model attributes)
        assert hasattr(data, "metrics")
        assert hasattr(data, "detection_log")
        assert hasattr(data, "species_frequency")
        assert hasattr(data, "hourly_distribution")
        assert hasattr(data, "visualization_data")
        assert hasattr(data, "system_status")

        # Verify metrics contain data
        metrics = data.metrics
        assert metrics.species_detected != "0"
        assert metrics.detections_today != "0"
        assert "GB" in metrics.storage
        assert "≥" in metrics.threshold

        # Verify detection log has entries
        assert len(data.detection_log) > 0
        assert all(hasattr(d, "time") for d in data.detection_log)
        assert all(hasattr(d, "species") for d in data.detection_log)
        assert all(hasattr(d, "confidence") for d in data.detection_log)
        assert all("%" in d.confidence for d in data.detection_log)

        # Verify species frequency data
        if data.species_frequency:
            assert all(hasattr(s, "name") for s in data.species_frequency)
            assert all(hasattr(s, "count") for s in data.species_frequency)
            assert all(hasattr(s, "bar_width") for s in data.species_frequency)
            # First species should have 100% bar width
            assert data.species_frequency[0].bar_width == "100%"

        # Verify hourly distribution is 24-hour array
        assert len(data.hourly_distribution) == 24
        assert all(isinstance(h, int) for h in data.hourly_distribution)

        # Verify visualization data format
        if data.visualization_data:
            assert all(hasattr(v, "x") for v in data.visualization_data)
            assert all(hasattr(v, "y") for v in data.visualization_data)
            assert all(hasattr(v, "species") for v in data.visualization_data)
            assert all(hasattr(v, "color") for v in data.visualization_data)
            # Check color values are valid
            valid_colors = ["#2e7d32", "#f57c00", "#c62828", "#666"]
            assert all(v.color in valid_colors for v in data.visualization_data)

        # Verify system status
        sys_status = data.system_status
        assert sys_status.cpu.percent == 45.5
        assert sys_status.cpu.temp == 55.0
        assert sys_status.memory.percent == 60.0
        assert sys_status.memory.used_gb == pytest.approx(4.0, rel=0.01)
        assert sys_status.disk.percent == 75.0
        assert sys_status.uptime == "2"  # Numeric value, suffix added in template

    @pytest.mark.asyncio
    async def test_temporal_patterns_integration(self, presentation_manager):
        """Test temporal patterns are correctly calculated from real data."""
        # Only get temporal patterns, not the entire landing page data
        analytics = presentation_manager.analytics_manager
        temporal = await analytics.get_temporal_patterns()

        hourly_dist = temporal["hourly_distribution"]

        # Should have detections spread across hours
        assert sum(hourly_dist) > 0

        # Check that at least some hours have detections
        hours_with_detections = sum(1 for h in hourly_dist if h > 0)
        assert hours_with_detections > 0

    @pytest.mark.asyncio
    async def test_species_frequency_sorting(self, presentation_manager):
        """Test that species are sorted by frequency."""
        # Only get species frequency data, not the entire landing page
        analytics = presentation_manager.analytics_manager
        frequency = await analytics.get_species_frequency_analysis()

        # Format it the same way as the presentation manager would
        species_freq = presentation_manager._format_species_list(frequency[:12])

        if len(species_freq) > 1:
            # Verify descending order by count
            counts = [s.count for s in species_freq]
            assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_detection_log_recent(self, presentation_manager):
        """Test that detection log shows recent detections."""
        # Only get recent detections, not the entire landing page
        recent = await presentation_manager.detection_query_service.query_detections(limit=10)

        # Format it the same way as the presentation manager would
        detection_log = presentation_manager._format_detection_log(recent)

        # Should be limited to 10 recent detections
        assert len(detection_log) <= 10

        # All should have required fields formatted correctly
        for detection in detection_log:
            assert ":" in detection.time  # HH:MM format
            assert "%" in detection.confidence  # Percentage format
            # DetectionLogEntry doesn't have a count field - it shows individual detections


class TestAPIResponseIntegration:
    """Test API response formatting with real data."""

    @pytest.mark.asyncio
    async def test_format_api_response_with_real_data(self, presentation_manager):
        """Test API response formatting with actual analytics data."""
        # Get real analytics data
        analytics = presentation_manager.analytics_manager
        summary = await analytics.get_dashboard_summary()

        # Format as API response
        response = presentation_manager.format_api_response(summary)

        assert response.status == "success"
        assert hasattr(response, "timestamp")
        assert response.data == summary

        # Verify data contains expected keys
        assert "species_total" in response.data
        assert "detections_today" in response.data
        assert "species_week" in response.data
        assert "storage_gb" in response.data
        assert "hours_monitored" in response.data
        assert "confidence_threshold" in response.data

    @pytest.mark.asyncio
    async def test_format_error_response(self, presentation_manager):
        """Test error response formatting."""
        error_data = {"error": "Database connection failed", "code": 500}

        response = presentation_manager.format_api_response(error_data, status="error")

        assert response.status == "error"
        assert response.data["error"] == "Database connection failed"
        assert response.data["code"] == 500


class TestFormattingWithRealData:
    """Test formatting methods with real database data."""

    @pytest.mark.asyncio
    async def test_format_metrics_with_real_summary(self, presentation_manager):
        """Test metrics formatting with real summary data."""
        analytics = presentation_manager.analytics_manager
        summary = await analytics.get_dashboard_summary()

        formatted = presentation_manager._format_metrics(summary)

        # Check all fields are formatted
        assert (
            "," in formatted.species_detected
            or int(formatted.species_detected.replace(",", "")) < 1000
        )
        assert "GB" in formatted.storage
        assert "≥" in formatted.threshold

        # Verify numeric values are reasonable
        hours_value = int(formatted.hours)
        assert hours_value >= 0

    @pytest.mark.asyncio
    async def test_format_species_list_with_real_data(self, presentation_manager):
        """Test species list formatting with real frequency data."""
        analytics = presentation_manager.analytics_manager
        frequency_data = await analytics.get_species_frequency_analysis(hours=24)

        if frequency_data:
            formatted = presentation_manager._format_species_list(frequency_data[:12])

            # Verify bar widths are calculated correctly
            max_count = frequency_data[0]["count"]
            for i, species in enumerate(formatted):
                expected_width = f"{(frequency_data[i]['count'] / max_count * 100):.0f}%"
                assert species.bar_width == expected_width

    @pytest.mark.asyncio
    async def test_format_scatter_data_with_real_detections(self, presentation_manager):
        """Test scatter data formatting with real detection data."""
        analytics = presentation_manager.analytics_manager
        scatter_data = await analytics.get_detection_scatter_data(hours=24)

        if scatter_data:
            formatted = presentation_manager._format_scatter_data(scatter_data)

            # Verify all points have correct structure
            for point in formatted:
                assert 0 <= point.x < 24  # Time in hours
                assert 0 <= point.y <= 1  # Confidence
                assert point.species  # Has species name
                assert point.color in ["#2e7d32", "#f57c00", "#c62828", "#666"]
