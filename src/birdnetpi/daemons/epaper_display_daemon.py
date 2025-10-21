"""E-paper display daemon for Waveshare HAT.

This daemon runs the e-paper display service, which shows system status
and bird detections on a Waveshare 2-color e-paper HAT. It is designed
to run only on single-board computers with the appropriate hardware.
"""

import asyncio
import logging
import signal

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.display.epaper import EPaperDisplayService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

logger = logging.getLogger(__name__)


class DaemonState:
    """Encapsulates daemon state to avoid module-level globals."""

    shutdown_flag: bool = False

    @classmethod
    def reset(cls) -> None:
        """Reset state to initial values (useful for testing)."""
        cls.shutdown_flag = False


def _signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully."""
    signal_name = (
        signal.Signals(signum).name if signum in signal.Signals._value2member_map_ else str(signum)
    )
    logger.info("Signal %s (%s) received, initiating graceful shutdown...", signal_name, signum)
    DaemonState.shutdown_flag = True


async def main_async() -> None:
    """Async main function that wraps the EPaperDisplayService."""
    logger.info("Starting e-paper display daemon")

    # Initialize services
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    db_service = CoreDatabaseService(path_resolver.get_database_path())

    # Initialize e-paper display service
    display_service = EPaperDisplayService(config, path_resolver, db_service)

    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Create a task for the display service
        display_task = asyncio.create_task(display_service.start())

        # Wait for shutdown signal
        while not DaemonState.shutdown_flag:
            await asyncio.sleep(0.1)

        # Cancel the display task
        display_task.cancel()
        try:
            await display_task
        except asyncio.CancelledError:
            pass

    except Exception:
        logger.exception("Error in e-paper display daemon")
    finally:
        await display_service.stop()
        logger.info("E-paper display daemon stopped")


def main() -> None:
    """Run the e-paper display daemon."""
    # Configure structlog first thing in main
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    configure_structlog(config)

    logger.info("E-paper display daemon starting")

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception:
        logger.exception("Error in main")
    finally:
        logger.info("E-paper display daemon exiting")


if __name__ == "__main__":
    main()
