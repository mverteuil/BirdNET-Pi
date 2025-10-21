"""E-paper display service for Waveshare 2-color HAT.

On SBC with the e-paper HAT installed, install the optional epaper dependencies:
    uv pip install -e .[epaper]

The service will run in simulation mode without hardware, saving display
output to a PNG file for testing purposes.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

import aiohttp
import psutil
from PIL import Image, ImageDraw, ImageFont

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class EPaperDisplayService:
    """Service for displaying BirdNET-Pi status on a Waveshare 2-color e-paper HAT.

    This service is designed to run only on single-board computers (SBC) with
    the Waveshare e-paper HAT attached. It displays:
    - System statistics (CPU, memory, disk usage)
    - System health status
    - Recent bird detections
    - Visual notification when new detections occur
    """

    # Display dimensions for Waveshare 2.13" v4 (250x122)
    DISPLAY_WIDTH = 250
    DISPLAY_HEIGHT = 122

    # Colors for 2-color display
    COLOR_WHITE = 255
    COLOR_BLACK = 0
    COLOR_RED = 128  # Simulated as gray for 2-color, actual red on hardware

    def __init__(
        self,
        config: BirdNETConfig,
        path_resolver: PathResolver,
        db_service: CoreDatabaseService,
    ) -> None:
        """Initialize the e-paper display service.

        Args:
            config: Application configuration
            path_resolver: Path resolver for system paths
            db_service: Database service for accessing detections
        """
        self.config = config
        self.path_resolver = path_resolver
        self.db_service = db_service
        self._shutdown_flag = False
        self._epd = None
        self._last_detection_id: uuid.UUID | None = None
        self._animation_frames = 0

        # Try to import Waveshare library
        try:
            # For Waveshare 2.13" v4 (red/black/white)
            from waveshare_epd import epd2in13_V4  # type: ignore[import-not-found]

            self._epd_module = epd2in13_V4
            self._has_hardware = True
            logger.info("Waveshare e-paper hardware detected")
        except (ImportError, OSError) as e:
            logger.warning("Waveshare e-paper hardware not available: %s", e)
            self._has_hardware = False
            self._epd_module = None

    def _init_display(self) -> None:
        """Initialize the e-paper display hardware."""
        if not self._has_hardware or self._epd_module is None:
            logger.info("Running in simulation mode (no hardware)")
            return

        try:
            self._epd = self._epd_module.EPD()
            self._epd.init()
            self._epd.Clear()
            logger.info("E-paper display initialized")
        except Exception:
            logger.exception("Failed to initialize e-paper display")
            self._has_hardware = False

    def _create_image(self) -> Image.Image:
        """Create a new blank image for drawing.

        Returns:
            PIL Image object with white background
        """
        return Image.new("1", (self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT), self.COLOR_WHITE)

    def _get_font(self, size: int = 12) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get a font for drawing text.

        Args:
            size: Font size in points

        Returns:
            Font object (TrueType if available, default otherwise)
        """
        try:
            # Try to use DejaVu Sans Mono (common on Linux)
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
        except OSError:
            try:
                # Fallback to Liberation Mono
                return ImageFont.truetype(
                    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", size
                )
            except OSError:
                # Use default font
                return ImageFont.load_default()

    def _get_system_stats(self) -> dict[str, Any]:
        """Collect current system statistics.

        Returns:
            Dictionary with CPU, memory, and disk statistics
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": memory.used / (1024**3),
            "memory_total_gb": memory.total / (1024**3),
            "disk_percent": disk.percent,
            "disk_used_gb": disk.used / (1024**3),
            "disk_total_gb": disk.total / (1024**3),
        }

    async def _get_health_status(self) -> dict[str, Any]:
        """Fetch system health status from the health API.

        Returns:
            Dictionary with health status information
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8000/api/health/ready") as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": data.get("status", "unknown"),
                            "database": data.get("checks", {}).get("database", False),
                        }
                    else:
                        return {"status": "unhealthy", "database": False}
        except Exception as e:
            logger.warning("Failed to fetch health status: %s", e)
            return {"status": "error", "database": False}

    async def _get_latest_detection(self) -> Detection | None:
        """Get the most recent detection from the database.

        Returns:
            Latest detection or None if no detections exist
        """
        try:
            async with self.db_service.get_async_db() as session:
                from sqlmodel import desc, select

                statement = select(Detection).order_by(desc(Detection.id)).limit(1)
                result = await session.execute(statement)
                return result.scalar_one_or_none()
        except Exception:
            logger.exception("Failed to fetch latest detection")
            return None

    def _draw_status_screen(
        self,
        stats: dict[str, Any],
        health: dict[str, Any],
        detection: Detection | None,
        show_animation: bool = False,
    ) -> Image.Image:
        """Draw the main status screen.

        Args:
            stats: System statistics
            health: Health status information
            detection: Latest detection (if any)
            show_animation: Whether to show detection animation

        Returns:
            PIL Image ready for display
        """
        image = self._create_image()
        draw = ImageDraw.Draw(image)

        font_small = self._get_font(10)
        font_medium = self._get_font(12)
        font_large = self._get_font(16)

        y_offset = 0

        # Header with site name and timestamp
        header_text = self.config.site_name[:20]  # Limit length
        draw.text((2, y_offset), header_text, font=font_large, fill=self.COLOR_BLACK)

        timestamp = datetime.now().strftime("%H:%M")
        draw.text((200, y_offset), timestamp, font=font_medium, fill=self.COLOR_BLACK)
        y_offset += 18

        # System stats
        draw.text(
            (2, y_offset),
            f"CPU: {stats['cpu_percent']:.1f}%",
            font=font_small,
            fill=self.COLOR_BLACK,
        )
        draw.text(
            (80, y_offset),
            f"MEM: {stats['memory_percent']:.1f}%",
            font=font_small,
            fill=self.COLOR_BLACK,
        )
        draw.text(
            (160, y_offset),
            f"DSK: {stats['disk_percent']:.1f}%",
            font=font_small,
            fill=self.COLOR_BLACK,
        )
        y_offset += 12

        # Health status
        health_symbol = "✓" if health.get("status") == "ready" else "✗"
        db_symbol = "✓" if health.get("database") else "✗"
        draw.text(
            (2, y_offset),
            f"Health: {health_symbol}  DB: {db_symbol}",
            font=font_small,
            fill=self.COLOR_BLACK,
        )
        y_offset += 14

        # Separator line
        draw.line([(0, y_offset), (self.DISPLAY_WIDTH, y_offset)], fill=self.COLOR_BLACK)
        y_offset += 4

        # Latest detection
        if detection:
            # Animation effect - blink/highlight when new detection
            if show_animation:
                # Draw a box around the detection info
                draw.rectangle(
                    (0, y_offset, self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT),
                    outline=self.COLOR_BLACK,
                    width=2,
                )
                y_offset += 4

            draw.text(
                (2, y_offset),
                "Latest Detection:",
                font=font_small,
                fill=self.COLOR_BLACK,
            )
            y_offset += 12

            # Bird name (truncate if too long)
            bird_name = detection.common_name[:30] if detection.common_name else "Unknown"
            draw.text((2, y_offset), bird_name, font=font_medium, fill=self.COLOR_BLACK)
            y_offset += 14

            # Confidence and time
            confidence_text = f"{detection.confidence * 100:.1f}%"
            time_text = detection.timestamp.strftime("%H:%M:%S")
            draw.text(
                (2, y_offset),
                f"{confidence_text} at {time_text}",
                font=font_small,
                fill=self.COLOR_BLACK,
            )
        else:
            draw.text(
                (2, y_offset),
                "No detections yet",
                font=font_small,
                fill=self.COLOR_BLACK,
            )

        return image

    def _update_display(self, image: Image.Image) -> None:
        """Update the physical e-paper display with the given image.

        Args:
            image: PIL Image to display
        """
        if not self._has_hardware or self._epd is None:
            # In simulation mode, save to file for testing
            output_path = self.path_resolver.get_data_dir() / "display_output.png"
            image.save(output_path)
            logger.debug("Display image saved to %s", output_path)
            return

        try:
            # Convert image to display format and update
            self._epd.display(self._epd.getbuffer(image))
            logger.debug("Display updated")
        except Exception:
            logger.exception("Failed to update e-paper display")

    async def _check_for_new_detection(self) -> bool:
        """Check if there's a new detection since last check.

        Returns:
            True if a new detection was found
        """
        latest = await self._get_latest_detection()
        if latest is None:
            return False

        # Check if this is a new detection
        if self._last_detection_id is None or latest.id != self._last_detection_id:
            self._last_detection_id = latest.id
            return True

        return False

    async def _display_loop(self) -> None:
        """Run the main display update loop."""
        logger.info("Starting e-paper display loop")

        while not self._shutdown_flag:
            try:
                # Gather data
                stats = self._get_system_stats()
                health = await self._get_health_status()
                detection = await self._get_latest_detection()

                # Check for new detections
                is_new_detection = await self._check_for_new_detection()

                # Show animation for 3 refresh cycles after new detection
                show_animation = False
                if is_new_detection:
                    self._animation_frames = 3
                    logger.info("New detection: %s", detection.common_name if detection else "None")

                if self._animation_frames > 0:
                    show_animation = True
                    self._animation_frames -= 1

                # Draw and update display
                image = self._draw_status_screen(stats, health, detection, show_animation)
                self._update_display(image)

                # Update based on configured interval (e-paper has limited refresh cycles)
                await asyncio.sleep(self.config.epaper_refresh_interval)

            except Exception:
                logger.exception("Error in display loop")
                await asyncio.sleep(5)

    async def start(self) -> None:
        """Start the e-paper display service."""
        logger.info("Initializing e-paper display service")
        self._init_display()
        self._shutdown_flag = False

        # Start the display loop
        await self._display_loop()

    async def stop(self) -> None:
        """Stop the e-paper display service and cleanup."""
        logger.info("Stopping e-paper display service")
        self._shutdown_flag = True

        # Clear and sleep the display
        if self._has_hardware and self._epd is not None:
            try:
                self._epd.Clear()
                self._epd.sleep()
                logger.info("E-paper display cleared and put to sleep")
            except Exception:
                logger.exception("Error during display cleanup")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        while not self._shutdown_flag:
            await asyncio.sleep(0.1)
