import asyncio
import logging

from birdnetpi.audio.audio_websocket_service import AudioWebSocketService
from birdnetpi.config import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

# Logger will be configured when main runs
logger = logging.getLogger(__name__)


async def main_async() -> None:
    """Async main function that wraps the AudioWebSocketService."""
    logger.info("Starting audio websocket daemon.")

    path_resolver = PathResolver()
    service = AudioWebSocketService(path_resolver)

    try:
        await service.start()
        await service.wait_for_shutdown()
    except Exception:
        logger.exception("Error in audio websocket daemon")
    finally:
        await service.stop()


def main() -> None:
    """Run the audio websocket daemon."""
    # Configure structlog first thing in main
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    configure_structlog(config)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception:
        logger.exception("Error in main")


if __name__ == "__main__":
    main()
