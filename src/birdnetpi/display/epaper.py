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
from typing import Any, ClassVar

import aiohttp
import psutil
from PIL import Image, ImageDraw, ImageFont, ImageOps

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_utils import SystemUtils

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

    # Display dimensions for Waveshare 2.13" displays (250x122)
    DISPLAY_WIDTH = 250
    DISPLAY_HEIGHT = 122

    # Colors for display (values depend on display type)
    COLOR_WHITE = 255
    COLOR_BLACK = 0
    COLOR_RED = 128  # For 3-color displays; simulated as gray for 2-color

    # Supported display type mapping
    DISPLAY_MODULES: ClassVar[dict[str, str]] = {
        "2in13_V4": "epd2in13_V4",  # 2-color (Black/White)
        "2in13b_V3": "epd2in13b_V3",  # 3-color (Black/White/Red) V3
        "2in13b_V4": "epd2in13b_V4",  # 3-color (Black/White/Red) V4
    }

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

        # Try to import Waveshare library based on config
        display_type = self.config.epaper_display_type
        module_name = self.DISPLAY_MODULES.get(display_type)

        # Determine if this is a color display based on config
        # (before attempting hardware import, so simulation mode works correctly)
        self._is_color_display = "b" in display_type.lower()  # 'b' variants support red

        if not module_name:
            logger.error(
                "Unsupported display type '%s'. Supported types: %s",
                display_type,
                ", ".join(self.DISPLAY_MODULES.keys()),
            )
            self._has_hardware = False
            self._epd_module = None
            return

        try:
            # Dynamically import the correct display module
            epd_module = __import__("waveshare_epd", fromlist=[module_name])
            self._epd_module = getattr(epd_module, module_name)
            self._has_hardware = True
            logger.info(
                "Waveshare e-paper hardware detected: %s (%s)",
                display_type,
                "3-color" if self._is_color_display else "2-color",
            )
        except (ImportError, OSError, AttributeError) as e:
            logger.warning(
                "Waveshare e-paper hardware not available for type '%s': %s", display_type, e
            )
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
            # Extract API base URL from detections_endpoint config
            # Default to port 8000 if config not available
            api_url = "http://localhost:8000"
            if hasattr(self.config, "detections_endpoint") and self.config.detections_endpoint:
                # Parse endpoint like "http://127.0.0.1:8888/api/detections/"
                # to get base URL "http://127.0.0.1:8888"
                endpoint = self.config.detections_endpoint
                if "/api/" in endpoint:
                    api_url = endpoint.split("/api/")[0]

            async with aiohttp.ClientSession() as session:
                health_url = f"{api_url}/api/health/ready"
                async with session.get(health_url) as response:
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
        animation_frame: int = 0,
    ) -> tuple[Image.Image, Image.Image | None]:
        """Draw the main status screen.

        Args:
            stats: System statistics
            health: Health status information
            detection: Latest detection (if any)
            show_animation: Whether to show detection animation
            animation_frame: Current animation frame number (for zigzag effect)

        Returns:
            Tuple of (black_image, red_image) for display.
            For 2-color displays, red_image will be None.
        """
        # Create black layer (all displays)
        black_image = self._create_image()
        black_draw = ImageDraw.Draw(black_image)

        # Create red layer (only for 3-color displays)
        red_image = None
        red_draw = None
        if self._is_color_display:
            red_image = self._create_image()
            red_draw = ImageDraw.Draw(red_image)

        # For backwards compatibility, use black_draw as default
        draw = black_draw

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

        # Latest detection
        if detection:
            # Animation effect - highlight when new detection
            if show_animation and self._is_color_display and red_draw:
                # Zigzag effect: alternate box position left/right based on frame
                # Creates a subtle "attention-grabbing" animation
                zigzag_offset = 3 if animation_frame % 2 == 0 else -3

                # Draw red box around detection info for 3-color displays
                # Start right below the separator line (y_offset + 1)
                red_draw.rectangle(
                    (
                        zigzag_offset,
                        y_offset + 1,
                        self.DISPLAY_WIDTH + zigzag_offset,
                        self.DISPLAY_HEIGHT,
                    ),
                    outline=self.COLOR_BLACK,
                    width=2,
                )
            elif show_animation:
                # Zigzag effect for 2-color displays
                zigzag_offset = 3 if animation_frame % 2 == 0 else -3

                # Draw black box for 2-color displays
                # Start right below the separator line (y_offset + 1)
                draw.rectangle(
                    (
                        zigzag_offset,
                        y_offset + 1,
                        self.DISPLAY_WIDTH + zigzag_offset,
                        self.DISPLAY_HEIGHT,
                    ),
                    outline=self.COLOR_BLACK,
                    width=2,
                )

            # Add spacing for content inside the box
            y_offset += 4

            # Detection header - use red for 3-color displays when animated
            header_draw = red_draw if (show_animation and red_draw) else draw
            header_draw.text(
                (2, y_offset),
                "Latest Detection:",
                font=font_small,
                fill=self.COLOR_BLACK,
            )
            y_offset += 12

            # Bird name - use red for 3-color displays when animated
            bird_name = detection.common_name[:30] if detection.common_name else "Unknown"
            name_draw = red_draw if (show_animation and red_draw) else draw
            name_draw.text((2, y_offset), bird_name, font=font_medium, fill=self.COLOR_BLACK)
            y_offset += 14

            # Confidence and time - always black
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

        return black_image, red_image

    def _create_composite_image(
        self, black_image: Image.Image, red_image: Image.Image | None
    ) -> Image.Image:
        """Create a composite RGB image showing black and red layers with proper colors.

        Args:
            black_image: PIL Image for black layer (mode "1")
            red_image: Optional PIL Image for red layer (mode "1")

        Returns:
            RGB composite image showing what a 3-color e-paper display would show
        """
        # Start with white background
        composite = Image.new("RGB", (self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT), (255, 255, 255))

        # Paste red layer first (if exists)
        if red_image:
            red_layer = Image.new("RGB", red_image.size, (255, 0, 0))
            # Use inverted red_image as mask: 0=black (paste), 255=white (don't paste)
            mask = ImageOps.invert(red_image.convert("L"))
            composite.paste(red_layer, (0, 0), mask)

        # Paste black layer second (overlays red where both exist)
        black_layer = Image.new("RGB", black_image.size, (0, 0, 0))
        mask = ImageOps.invert(black_image.convert("L"))
        composite.paste(black_layer, (0, 0), mask)

        return composite

    def _update_display(
        self, black_image: Image.Image, red_image: Image.Image | None = None
    ) -> None:
        """Update the physical e-paper display with the given image(s).

        Args:
            black_image: PIL Image for black layer
            red_image: Optional PIL Image for red layer (3-color displays only)
        """
        if not self._has_hardware or self._epd is None:
            # In simulation mode, only save files if running in Docker
            # On SBC without hardware, skip file writes to avoid excessive disk wear
            if SystemUtils.is_docker_environment():
                simulator_dir = self.path_resolver.get_display_simulator_dir()
                simulator_dir.mkdir(parents=True, exist_ok=True)
                black_path = simulator_dir / "display_output_black.png"
                black_image.save(black_path)
                logger.debug("Display black layer saved to %s", black_path)

                if red_image:
                    red_path = simulator_dir / "display_output_red.png"
                    red_image.save(red_path)
                    logger.debug("Display red layer saved to %s", red_path)

                # Generate composite image showing final display output
                composite = self._create_composite_image(black_image, red_image)
                comp_path = simulator_dir / "display_output_comp.png"
                composite.save(comp_path)
                logger.debug("Display composite saved to %s", comp_path)
            else:
                logger.debug(
                    "Skipping simulation file writes on SBC (no hardware detected, not in Docker)"
                )
            return

        try:
            if self._is_color_display and red_image:
                # 3-color display: send both black and red buffers
                self._epd.display(self._epd.getbuffer(black_image), self._epd.getbuffer(red_image))
                logger.debug("3-color display updated (black + red)")
            else:
                # 2-color display: send only black buffer
                self._epd.display(self._epd.getbuffer(black_image))
                logger.debug("2-color display updated")
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

                # Show animation for 12 refresh cycles after new detection
                show_animation = False
                animation_frame = 0
                if is_new_detection:
                    self._animation_frames = 12
                    logger.info("New detection: %s", detection.common_name if detection else "None")

                if self._animation_frames > 0:
                    show_animation = True
                    # Calculate which frame we're on (0-11) for zigzag effect
                    animation_frame = 12 - self._animation_frames
                    self._animation_frames -= 1

                # Draw and update display
                black_image, red_image = self._draw_status_screen(
                    stats, health, detection, show_animation, animation_frame
                )
                self._update_display(black_image, red_image)

                # Use faster refresh during animation (2 seconds) for better visibility
                # Normal refresh otherwise (default 30 seconds) to preserve e-paper lifespan
                if self._animation_frames > 0:
                    await asyncio.sleep(2)  # Fast refresh during animation
                else:
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
