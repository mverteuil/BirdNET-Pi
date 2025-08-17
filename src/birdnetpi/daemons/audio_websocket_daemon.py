import asyncio
import logging

from birdnetpi.audio.audio_websocket_service import AudioWebSocketService
from birdnetpi.utils.path_resolver import PathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main_async() -> None:
    """Async main function that wraps the AudioWebSocketService."""
    logger.info("Starting audio websocket daemon.")

    path_resolver = PathResolver()
    service = AudioWebSocketService(path_resolver)

    try:
        await service.start()
        await service.wait_for_shutdown()
    except Exception as e:
        logger.error("Error in audio websocket daemon: %s", e, exc_info=True)
    finally:
        await service.stop()


def main() -> None:
    """Run the audio websocket daemon."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error("Error in main: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
