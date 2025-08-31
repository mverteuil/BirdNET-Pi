"""Unit tests for PresentationManager."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import Detection


@pytest.fixture
def mock_analytics_manager():
    """Create a mock AnalyticsManager."""
    manager = MagicMock(spec=AnalyticsManager)
    manager.data_manager = MagicMock()
    return manager


@pytest.fixture
def mock_config():
    """Create a mock BirdNETConfig."""
    config = MagicMock(spec=BirdNETConfig)
    config.species_confidence_threshold = 0.7
    return config


@pytest.fixture
def presentation_manager(mock_analytics_manager, mock_config):
    """Create a PresentationManager with mocked dependencies."""
    return PresentationManager(mock_analytics_manager, mock_config)


@pytest.fixture
def sample_detections():
    """Create sample detection objects for testing."""
    return [
        Detection(
            species_tensor="Turdus migratorius_American Robin",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2024, 1, 1, 10, 30, 0),
        ),
        Detection(
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            confidence=0.88,
            timestamp=datetime(2024, 1, 1, 11, 15, 0),
        ),
        Detection(
            species_tensor="Unknown species",
            scientific_name="Unknown species",
            common_name=None,  # No common name
            confidence=0.65,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
    ]


class TestLandingPageData:
    """Test landing page data preparation."""

    @pytest.mark.asyncio
    @patch("birdnetpi.analytics.presentation.AudioDeviceService")
    @patch("birdnetpi.analytics.presentation.SystemInspector")
    async def test_get_landing_page_data(
        self,
        mock_inspector,
        mock_audio_service,
        presentation_manager,
        mock_analytics_manager,
        sample_detections,
    ):
        """Test complete landing page data assembly."""
        # Configure SystemInspector mocks
        mock_inspector.get_cpu_usage.return_value = 45.5
        mock_inspector.get_cpu_temperature.return_value = 55.2
        mock_inspector.get_memory_usage.return_value = {
            "percent": 65.0,
            "used": 2147483648,  # 2GB
            "total": 3221225472,  # 3GB
        }
        mock_inspector.get_disk_usage.return_value = {
            "percent": 80.0,
            "used": 107374182400,  # 100GB
            "total": 134217728000,  # 125GB
        }
        mock_inspector.get_system_info.return_value = {
            "boot_time": 1704067200.0,  # 2024-01-01 00:00:00
        }

        # Configure AudioDeviceService mock
        mock_audio_device = MagicMock()
        mock_audio_device.name = "Test USB Audio"
        mock_audio_service_instance = mock_audio_service.return_value
        mock_audio_service_instance.discover_input_devices.return_value = [mock_audio_device]

        # Configure analytics manager mocks (as async)
        mock_analytics_manager.get_dashboard_summary = AsyncMock(
            return_value={
                "species_total": 150,
                "detections_today": 25,
                "species_week": 35,
                "storage_gb": 5.5,
                "hours_monitored": 120.0,
                "confidence_threshold": 0.7,
            }
        )

        mock_analytics_manager.get_species_frequency_analysis = AsyncMock(
            return_value=[
                {"name": "American Robin", "count": 50, "percentage": 40.0, "category": "common"},
                {
                    "name": "Northern Cardinal",
                    "count": 30,
                    "percentage": 24.0,
                    "category": "regular",
                },
                {"name": "Blue Jay", "count": 20, "percentage": 16.0, "category": "regular"},
            ]
        )

        mock_analytics_manager.get_temporal_patterns = AsyncMock(
            return_value={
                "hourly_distribution": [
                    0,
                    0,
                    0,
                    0,
                    0,
                    10,
                    15,
                    25,
                    20,
                    18,
                    12,
                    8,
                    5,
                    3,
                    2,
                    1,
                    1,
                    2,
                    4,
                    6,
                    5,
                    3,
                    2,
                    0,
                ],
                "peak_hour": 7,
                "periods": {
                    "night_early": 0,
                    "dawn": 50,
                    "morning": 63,
                    "afternoon": 11,
                    "evening": 12,
                    "night_late": 14,
                },
            }
        )

        # Mock data_manager methods
        mock_analytics_manager.data_manager.get_recent_detections = AsyncMock(
            return_value=sample_detections
        )
        mock_analytics_manager.data_manager.query_detections = AsyncMock(
            return_value=sample_detections
        )

        mock_analytics_manager.get_detection_scatter_data = AsyncMock(
            return_value=[
                {
                    "time": 6.25,
                    "confidence": 0.95,
                    "species": "American Robin",
                    "frequency_category": "common",
                },
                {
                    "time": 7.5,
                    "confidence": 0.88,
                    "species": "Northern Cardinal",
                    "frequency_category": "regular",
                },
            ]
        )

        # Mock time for uptime calculation
        with patch("time.time", return_value=1704153600.0):  # 2024-01-02 00:00:00
            data = await presentation_manager.get_landing_page_data()

        # Verify structure (Pydantic model attributes)
        assert hasattr(data, "metrics")
        assert hasattr(data, "detection_log")
        assert hasattr(data, "species_frequency")
        assert hasattr(data, "hourly_distribution")
        assert hasattr(data, "visualization_data")
        assert hasattr(data, "system_status")

        # Verify metrics formatting
        assert data.metrics.species_detected == "150"
        assert data.metrics.detections_today == "25"
        assert data.metrics.species_week == "35"
        assert data.metrics.storage == "5.5 GB"
        assert data.metrics.hours == "120"
        assert data.metrics.threshold == "≥0.70"

        # Verify detection log
        assert len(data.detection_log) == 3
        assert data.detection_log[0].time == "10:30"
        assert data.detection_log[0].species == "American Robin"
        assert data.detection_log[0].confidence == "95%"

        # Verify species frequency (limited to 12)
        assert len(data.species_frequency) == 3
        assert data.species_frequency[0].name == "American Robin"
        assert data.species_frequency[0].count == 50
        assert data.species_frequency[0].bar_width == "100%"  # Highest count

        # Verify hourly distribution
        assert data.hourly_distribution == [
            0,
            0,
            0,
            0,
            0,
            10,
            15,
            25,
            20,
            18,
            12,
            8,
            5,
            3,
            2,
            1,
            1,
            2,
            4,
            6,
            5,
            3,
            2,
            0,
        ]

        # Verify visualization data
        assert len(data.visualization_data) == 2
        assert data.visualization_data[0].x == 6.25
        assert data.visualization_data[0].y == 0.95
        assert data.visualization_data[0].color == "#2e7d32"  # common = green

        # Verify system status
        assert data.system_status.cpu.percent == 45.5
        assert data.system_status.cpu.temp == 55.2
        assert data.system_status.memory.percent == 65.0
        assert data.system_status.uptime == "1"  # Numeric value only


class TestFormatting:
    """Test individual formatting methods."""

    def test_format_metrics(self, presentation_manager):
        """Test metrics formatting."""
        summary = {
            "species_total": 1250,
            "detections_today": 42,
            "species_week": 18,
            "storage_gb": 12.345,
            "hours_monitored": 168.5,
            "confidence_threshold": 0.85,
        }

        formatted = presentation_manager._format_metrics(summary)

        assert formatted.species_detected == "1,250"
        assert formatted.detections_today == "42"
        assert formatted.species_week == "18"
        assert formatted.storage == "12.3 GB"
        assert formatted.hours == "168"
        assert formatted.threshold == "≥0.85"

    def test_format_detection_log(self, presentation_manager, sample_detections):
        """Test detection log formatting."""
        formatted = presentation_manager._format_detection_log(sample_detections)

        assert len(formatted) == 3

        # Check first detection
        assert formatted[0].time == "10:30"
        assert formatted[0].species == "American Robin"
        assert formatted[0].confidence == "95%"

        # Check detection with no common name
        assert formatted[2].species == "Unknown species"  # Falls back to scientific name
        assert formatted[2].confidence == "65%"

    def test_format_detection_log_empty(self, presentation_manager):
        """Test detection log formatting with empty list."""
        formatted = presentation_manager._format_detection_log([])
        assert formatted == []

    def test_format_species_list(self, presentation_manager):
        """Test species list formatting."""
        frequency_data = [
            {"name": "Species A", "count": 100, "percentage": 50.0, "category": "common"},
            {"name": "Species B", "count": 60, "percentage": 30.0, "category": "regular"},
            {"name": "Species C", "count": 40, "percentage": 20.0, "category": "uncommon"},
        ]

        formatted = presentation_manager._format_species_list(frequency_data)

        assert len(formatted) == 3

        # First species should have 100% bar width (highest count)
        assert formatted[0].name == "Species A"
        assert formatted[0].count == 100
        assert formatted[0].bar_width == "100%"

        # Second species bar width relative to first
        assert formatted[1].bar_width == "60%"

        # Third species bar width relative to first
        assert formatted[2].bar_width == "40%"

    def test_format_species_list_empty(self, presentation_manager):
        """Test species list formatting with empty data."""
        formatted = presentation_manager._format_species_list([])
        assert formatted == []

    def test_format_scatter_data(self, presentation_manager):
        """Test scatter plot data formatting."""
        scatter_data = [
            {"time": 6.5, "confidence": 0.95, "species": "Robin", "frequency_category": "common"},
            {
                "time": 12.25,
                "confidence": 0.75,
                "species": "Cardinal",
                "frequency_category": "regular",
            },
            {
                "time": 18.75,
                "confidence": 0.60,
                "species": "Sparrow",
                "frequency_category": "uncommon",
            },
            {
                "time": 20.0,
                "confidence": 0.55,
                "species": "Unknown",
                "frequency_category": "rare",
            },  # Unknown category
        ]

        formatted = presentation_manager._format_scatter_data(scatter_data)

        assert len(formatted) == 4

        # Check color mapping for known categories
        assert formatted[0].color == "#2e7d32"  # common = green
        assert formatted[1].color == "#f57c00"  # regular = orange
        assert formatted[2].color == "#c62828"  # uncommon = red
        assert formatted[3].color == "#666"  # unknown category = gray

        # Check data transformation
        assert formatted[0].x == 6.5
        assert formatted[0].y == 0.95
        assert formatted[0].species == "Robin"


class TestSystemStatus:
    """Test system status monitoring."""

    @patch("birdnetpi.analytics.presentation.AudioDeviceService")
    @patch("birdnetpi.analytics.presentation.SystemInspector")
    @patch("time.time")
    def test_get_system_status(
        self, mock_time, mock_inspector, mock_audio_service, presentation_manager
    ):
        """Test system status retrieval and formatting."""
        # Configure time mock
        mock_time.return_value = 1704240000.0  # 2024-01-03 00:00:00

        # Configure SystemInspector mocks
        mock_inspector.get_cpu_usage.return_value = 35.7
        mock_inspector.get_cpu_temperature.return_value = 48.5
        mock_inspector.get_memory_usage.return_value = {
            "percent": 72.3,
            "used": 8589934592,  # 8GB
            "total": 17179869184,  # 16GB
        }
        mock_inspector.get_disk_usage.return_value = {
            "percent": 45.0,
            "used": 53687091200,  # 50GB
            "total": 107374182400,  # 100GB
        }
        mock_inspector.get_system_info.return_value = {
            "boot_time": 1703980800.0,  # 2023-12-31 00:00:00 (3 days ago)
        }

        # Configure AudioDeviceService mock
        mock_audio_device = MagicMock()
        mock_audio_device.name = "Test Audio Device"
        mock_audio_service_instance = mock_audio_service.return_value
        mock_audio_service_instance.discover_input_devices.return_value = [mock_audio_device]

        status = presentation_manager._get_system_status()

        # Verify CPU metrics
        assert status.cpu.percent == 35.7
        assert status.cpu.temp == 48.5

        # Verify memory metrics
        assert status.memory.percent == 72.3
        assert status.memory.used_gb == pytest.approx(8.0, rel=0.01)
        assert status.memory.total_gb == pytest.approx(16.0, rel=0.01)

        # Verify disk metrics
        assert status.disk.percent == 45.0
        assert status.disk.used_gb == pytest.approx(50.0, rel=0.01)
        assert status.disk.total_gb == pytest.approx(100.0, rel=0.01)

        # Verify audio device is retrieved from AudioDeviceService
        assert status.audio.level_db == -60  # Silence/no signal
        assert status.audio.device == "Test Audio Device"

        # Verify uptime calculation (numeric value only)
        assert status.uptime == "3"

    @patch("birdnetpi.analytics.presentation.AudioDeviceService")
    @patch("birdnetpi.analytics.presentation.SystemInspector")
    @patch("time.time")
    def test_get_system_status_no_temperature(
        self, mock_time, mock_inspector, mock_audio_service, presentation_manager
    ):
        """Test system status when temperature is not available."""
        mock_time.return_value = 1704240000.0

        # Configure mocks with no temperature
        mock_inspector.get_cpu_usage.return_value = 50.0
        mock_inspector.get_cpu_temperature.return_value = None  # No temperature sensor
        mock_inspector.get_memory_usage.return_value = {
            "percent": 50,
            "used": 1073741824,
            "total": 2147483648,
        }
        mock_inspector.get_disk_usage.return_value = {
            "percent": 50,
            "used": 5368709120,
            "total": 10737418240,
        }
        mock_inspector.get_system_info.return_value = {"boot_time": 1704153600.0}

        # Configure AudioDeviceService mock with no devices
        mock_audio_service_instance = mock_audio_service.return_value
        mock_audio_service_instance.discover_input_devices.return_value = []

        status = presentation_manager._get_system_status()

        # Should handle None temperature gracefully
        assert status.cpu.temp == 0

        # Should handle no audio devices gracefully
        assert status.audio.device == "No audio device"


class TestAPIFormatting:
    """Test API response formatting."""

    def test_format_api_response_success(self, presentation_manager):
        """Test successful API response formatting."""
        data = {"result": "test", "count": 42}

        with patch("birdnetpi.analytics.presentation.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            response = presentation_manager.format_api_response(data)

        assert response.status == "success"
        assert response.timestamp == "2024-01-01T12:00:00"
        assert response.data == data

    def test_format_api_response_error(self, presentation_manager):
        """Test error API response formatting."""
        error_data = {"error": "Not found"}

        with patch("birdnetpi.analytics.presentation.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
            response = presentation_manager.format_api_response(error_data, status="error")

        assert response.status == "error"
        assert response.timestamp == "2024-01-01T12:00:00"
        assert response.data == error_data

    def test_format_api_response_custom_status(self, presentation_manager):
        """Test API response with custom status."""
        data = {"message": "Processing"}

        response = presentation_manager.format_api_response(data, status="pending")

        assert response.status == "pending"
        assert response.data == data
        assert hasattr(response, "timestamp")
