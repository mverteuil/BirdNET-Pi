"""Tests for e-paper display service."""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import psutil
import pytest
from PIL import Image
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.display.epaper import EPaperDisplayService


class _AsyncContextManagerProtocol:
    """Protocol for async context managers."""

    async def __aenter__(self):
        """Enter async context."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        ...


class TestEPaperDisplayService:
    """Test the EPaperDisplayService class."""

    @pytest.fixture
    def mock_config(self) -> BirdNETConfig:
        """Create a mock configuration."""
        config = BirdNETConfig()
        config.site_name = "Test Site"
        config.epaper_refresh_interval = 1  # Fast refresh for testing
        return config

    @pytest.fixture
    def mock_db_service(self) -> Mock:
        """Create a mock database service."""
        return Mock(spec=CoreDatabaseService)

    @pytest.fixture
    def epaper_service_no_hardware(
        self, mock_config, path_resolver, mock_db_service
    ) -> EPaperDisplayService:
        """Create an e-paper service instance without hardware."""
        # The waveshare_epd module import is inside the __init__, so we patch it there
        with patch.dict("sys.modules", {"waveshare_epd": None}):
            service = EPaperDisplayService(mock_config, path_resolver, mock_db_service)
        return service

    def test_init_without_hardware(self, mock_config, path_resolver, mock_db_service):
        """Should fall back to simulation mode when hardware is not available."""
        with patch.dict("sys.modules", {"waveshare_epd": None}):
            service = EPaperDisplayService(mock_config, path_resolver, mock_db_service)

        assert service._has_hardware is False
        assert service._epd is None

    def test_create_image(self, epaper_service_no_hardware):
        """Should create a new blank image with correct dimensions."""
        image = epaper_service_no_hardware._create_image()

        assert isinstance(image, Image.Image)
        assert image.size == (
            EPaperDisplayService.DISPLAY_WIDTH,
            EPaperDisplayService.DISPLAY_HEIGHT,
        )
        assert image.mode == "1"

    def test_get_font(self, epaper_service_no_hardware):
        """Should retrieve a font for drawing text."""
        font = epaper_service_no_hardware._get_font(12)
        assert font is not None

    @patch("birdnetpi.display.epaper.psutil", autospec=True)
    def test_get_system_stats(self, mock_psutil, epaper_service_no_hardware):
        """Should collect current system statistics."""
        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 45.5

        # Create mock memory object with spec from real psutil return type
        mock_memory = MagicMock(spec=type(psutil.virtual_memory()))
        mock_memory.percent = 60.2
        mock_memory.used = 4 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_psutil.virtual_memory.return_value = mock_memory

        # Create mock disk object with spec from real psutil return type
        mock_disk = MagicMock(spec=type(psutil.disk_usage("/")))
        mock_disk.percent = 75.0
        mock_disk.used = 100 * 1024**3
        mock_disk.total = 200 * 1024**3
        mock_psutil.disk_usage.return_value = mock_disk

        stats = epaper_service_no_hardware._get_system_stats()

        assert stats["cpu_percent"] == 45.5
        assert stats["memory_percent"] == 60.2
        assert stats["disk_percent"] == 75.0
        assert "memory_used_gb" in stats
        assert "disk_used_gb" in stats

    @pytest.mark.asyncio
    async def test_get_health_status_success(self, epaper_service_no_hardware):
        """Should fetch health status successfully."""
        mock_response = MagicMock(spec=aiohttp.ClientResponse)
        mock_response.status = 200
        mock_response.json = AsyncMock(
            spec=object,
            return_value={
                "status": "ready",
                "checks": {"database": True},
            },
        )

        mock_get = AsyncMock(spec=_AsyncContextManagerProtocol)
        mock_get.__aenter__.return_value = mock_response
        mock_get.__aexit__.return_value = AsyncMock(spec=object)

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.get = MagicMock(spec=object, return_value=mock_get)

        with patch("aiohttp.ClientSession", autospec=True) as mock_session_cls:
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_session_cls.return_value.__aexit__.return_value = AsyncMock(spec=object)

            health = await epaper_service_no_hardware._get_health_status()

        assert health["status"] == "ready"
        assert health["database"] is True

    @pytest.mark.asyncio
    async def test_get_health_status_failure(self, epaper_service_no_hardware):
        """Should return unhealthy status when health check fails."""
        mock_response = MagicMock(spec=aiohttp.ClientResponse)
        mock_response.status = 503

        mock_get = AsyncMock(spec=_AsyncContextManagerProtocol)
        mock_get.__aenter__.return_value = mock_response
        mock_get.__aexit__.return_value = AsyncMock(spec=object)

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.get = MagicMock(spec=object, return_value=mock_get)

        with patch("aiohttp.ClientSession", autospec=True) as mock_session_cls:
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_session_cls.return_value.__aexit__.return_value = AsyncMock(spec=object)

            health = await epaper_service_no_hardware._get_health_status()

        assert health["status"] == "unhealthy"
        assert health["database"] is False

    @pytest.mark.asyncio
    async def test_get_latest_detection(self, epaper_service_no_hardware, mock_db_service):
        """Should fetch the most recent detection from database."""
        # Create a mock detection
        mock_detection = Detection(
            id=uuid.uuid4(),
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
            species_tensor="Turdus_migratorius_American Robin",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        # Mock the database session and result
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = AsyncMock(spec=Result)
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session.execute.return_value = mock_result

        # Mock the async context manager for get_async_db
        mock_context = AsyncMock(spec=_AsyncContextManagerProtocol)
        mock_context.__aenter__.return_value = mock_session
        epaper_service_no_hardware.db_service.get_async_db.return_value = mock_context

        detection = await epaper_service_no_hardware._get_latest_detection()

        assert detection is not None
        assert detection.common_name == "American Robin"
        assert detection.confidence == 0.85

    def test_draw_status_screen_no_detection(self, epaper_service_no_hardware):
        """Should draw status screen without any detection."""
        stats = {
            "cpu_percent": 45.5,
            "memory_percent": 60.2,
            "disk_percent": 75.0,
            "memory_used_gb": 4.0,
            "memory_total_gb": 8.0,
            "disk_used_gb": 100.0,
            "disk_total_gb": 200.0,
        }
        health = {"status": "ready", "database": True}

        black_image, red_image = epaper_service_no_hardware._draw_status_screen(
            stats, health, None, False, 0
        )

        assert isinstance(black_image, Image.Image)
        assert black_image.size == (
            EPaperDisplayService.DISPLAY_WIDTH,
            EPaperDisplayService.DISPLAY_HEIGHT,
        )
        # Red image should be None for non-color display or when no animation
        assert red_image is None or isinstance(red_image, Image.Image)

    def test_draw_status_screen_with_detection(self, epaper_service_no_hardware):
        """Should draw status screen with a detection."""
        stats = {
            "cpu_percent": 45.5,
            "memory_percent": 60.2,
            "disk_percent": 75.0,
            "memory_used_gb": 4.0,
            "memory_total_gb": 8.0,
            "disk_used_gb": 100.0,
            "disk_total_gb": 200.0,
        }
        health = {"status": "ready", "database": True}
        detection = Detection(
            id=uuid.uuid4(),
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
            species_tensor="Turdus_migratorius_American Robin",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        black_image, red_image = epaper_service_no_hardware._draw_status_screen(
            stats, health, detection, False, 0
        )

        assert isinstance(black_image, Image.Image)
        assert red_image is None or isinstance(red_image, Image.Image)

    def test_draw_status_screen_with_animation(self, epaper_service_no_hardware):
        """Should draw status screen with animation effect."""
        stats = {
            "cpu_percent": 45.5,
            "memory_percent": 60.2,
            "disk_percent": 75.0,
            "memory_used_gb": 4.0,
            "memory_total_gb": 8.0,
            "disk_used_gb": 100.0,
            "disk_total_gb": 200.0,
        }
        health = {"status": "ready", "database": True}
        detection = Detection(
            id=uuid.uuid4(),
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
            species_tensor="Turdus_migratorius_American Robin",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        black_image, red_image = epaper_service_no_hardware._draw_status_screen(
            stats, health, detection, True, 0
        )

        assert isinstance(black_image, Image.Image)
        # With animation on a color display, we should have a red image
        assert isinstance(red_image, Image.Image)

    def test_update_display_simulation_mode(self, epaper_service_no_hardware, path_resolver):
        """Should save display image files in simulation mode when in Docker."""
        black_image = epaper_service_no_hardware._create_image()
        red_image = epaper_service_no_hardware._create_image()

        # Mock Docker environment check to return True
        with patch("birdnetpi.display.epaper.SystemUtils.is_docker_environment", return_value=True):
            epaper_service_no_hardware._update_display(black_image, red_image)

        # Check that files were saved in display-simulator subdirectory
        simulator_dir = path_resolver.get_display_simulator_dir()
        assert (simulator_dir / "display_output_black.png").exists()
        assert (simulator_dir / "display_output_red.png").exists()
        assert (simulator_dir / "display_output_comp.png").exists()

    @pytest.mark.asyncio
    async def test_check_for_new_detection_first_detection(self, epaper_service_no_hardware):
        """Should detect new detection when it is the first one."""
        detection_id = uuid.uuid4()
        mock_detection = Detection(
            id=detection_id,
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
            species_tensor="Turdus_migratorius_American Robin",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        with patch.object(
            epaper_service_no_hardware,
            "_get_latest_detection",
            autospec=True,
            return_value=mock_detection,
        ):
            is_new = await epaper_service_no_hardware._check_for_new_detection()

        assert is_new is True
        assert epaper_service_no_hardware._last_detection_id == detection_id

    @pytest.mark.asyncio
    async def test_check_for_new_detection_no_new_detection(self, epaper_service_no_hardware):
        """Should return false when there is no new detection."""
        detection_id = uuid.uuid4()
        mock_detection = Detection(
            id=detection_id,
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
            species_tensor="Turdus_migratorius_American Robin",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        epaper_service_no_hardware._last_detection_id = detection_id

        with patch.object(
            epaper_service_no_hardware,
            "_get_latest_detection",
            autospec=True,
            return_value=mock_detection,
        ):
            is_new = await epaper_service_no_hardware._check_for_new_detection()

        assert is_new is False

    @pytest.mark.asyncio
    async def test_check_for_new_detection_newer_detection(self, epaper_service_no_hardware):
        """Should detect when there is a newer detection."""
        old_id = uuid.uuid4()
        new_id = uuid.uuid4()
        mock_detection = Detection(
            id=new_id,
            common_name="Blue Jay",
            scientific_name="Cyanocitta cristata",
            confidence=0.90,
            species_tensor="Cyanocitta_cristata_Blue Jay",
            timestamp=datetime.now(),
            latitude=42.0,
            longitude=-71.0,
        )

        epaper_service_no_hardware._last_detection_id = old_id

        with patch.object(
            epaper_service_no_hardware,
            "_get_latest_detection",
            autospec=True,
            return_value=mock_detection,
        ):
            is_new = await epaper_service_no_hardware._check_for_new_detection()

        assert is_new is True
        assert epaper_service_no_hardware._last_detection_id == new_id

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_display_loop_runs_and_stops(self, epaper_service_no_hardware):
        """Should run display loop and stop gracefully."""
        # Mock all the methods that the loop calls
        with (
            patch.object(
                epaper_service_no_hardware,
                "_get_system_stats",
                return_value={
                    "cpu_percent": 45.5,
                    "memory_percent": 60.2,
                    "disk_percent": 75.0,
                    "memory_used_gb": 4.0,
                    "memory_total_gb": 8.0,
                    "disk_used_gb": 100.0,
                    "disk_total_gb": 200.0,
                },
            ),
            patch.object(
                epaper_service_no_hardware,
                "_get_health_status",
                return_value={"status": "ready", "database": True},
            ),
            patch.object(
                epaper_service_no_hardware,
                "_get_latest_detection",
                autospec=True,
                return_value=None,
            ),
            patch.object(
                epaper_service_no_hardware, "_check_for_new_detection", return_value=False
            ),
            patch.object(epaper_service_no_hardware, "_update_display", autospec=True),
        ):
            # Start the loop in a task
            loop_task = asyncio.create_task(epaper_service_no_hardware._display_loop())

            # Let it run for a bit
            await asyncio.sleep(0.2)

            # Stop the loop
            epaper_service_no_hardware._shutdown_flag = True

            # Wait for the loop to finish
            await asyncio.wait_for(loop_task, timeout=2.0)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_start_and_stop(self, epaper_service_no_hardware):
        """Should start and stop the service cleanly."""

        # Mock the display loop to exit quickly
        async def mock_display_loop():
            await asyncio.sleep(0.1)

        with (
            patch.object(epaper_service_no_hardware, "_init_display", autospec=True),
            patch.object(
                epaper_service_no_hardware, "_display_loop", side_effect=mock_display_loop
            ),
        ):
            # Start the service in a task
            start_task = asyncio.create_task(epaper_service_no_hardware.start())

            # Let it run briefly
            await asyncio.sleep(0.2)

            # Stop it
            await epaper_service_no_hardware.stop()

            # Wait for start task to complete
            await asyncio.wait_for(start_task, timeout=2.0)

        assert epaper_service_no_hardware._shutdown_flag is True
