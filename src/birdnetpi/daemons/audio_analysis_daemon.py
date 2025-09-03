import asyncio
import atexit
import logging
import os
import signal
import time
from types import FrameType
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from birdnetpi.audio.analysis import AudioAnalysisManager
from birdnetpi.config import ConfigManager
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from birdnetpi.config import BirdNETConfig

logger = logging.getLogger(__name__)


class DaemonState:
    """Encapsulates daemon state to avoid module-level globals."""

    shutdown_flag: bool = False
    fifo_analysis_path: str | None = None
    fifo_analysis_fd: int | None = None
    session: "AsyncSession | None" = None
    event_loop: asyncio.AbstractEventLoop | None = None
    audio_analysis_service: AudioAnalysisManager | None = None

    @classmethod
    def reset(cls) -> None:
        """Reset state to initial values (useful for testing)."""
        cls.shutdown_flag = False
        cls.fifo_analysis_path = None
        cls.fifo_analysis_fd = None
        cls.session = None
        cls.event_loop = None
        cls.audio_analysis_service = None


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    DaemonState.shutdown_flag = True


def _cleanup_fifo() -> None:
    # Stop audio analysis manager first to ensure no ongoing processing
    if DaemonState.audio_analysis_service:
        try:
            DaemonState.audio_analysis_service.stop_buffer_flush_task()
            logger.info("Stopped audio analysis buffer flush task")
            # Give a moment for threads to finish
            time.sleep(0.2)
        except Exception as e:
            logger.debug("Error stopping buffer flush task: %s", e)

    # Close FIFO
    if DaemonState.fifo_analysis_fd:
        os.close(DaemonState.fifo_analysis_fd)
        logger.info("Closed FIFO: %s", DaemonState.fifo_analysis_path)
        DaemonState.fifo_analysis_fd = None

    # Clean up database session and event loop
    if DaemonState.event_loop and not DaemonState.event_loop.is_closed():
        if DaemonState.session:
            try:
                DaemonState.event_loop.run_until_complete(DaemonState.session.close())
            except Exception as e:
                logger.debug("Error closing session: %s", e)
        DaemonState.event_loop.close()


async def init_session_and_service(
    path_resolver: PathResolver, config: "BirdNETConfig"
) -> tuple["AsyncSession", AudioAnalysisManager]:
    """Initialize async session and audio analysis service."""
    # Create multilingual database service
    species_database = SpeciesDatabaseService(path_resolver)
    logger.info("Multilingual database service initialized")

    # Create async session for database queries
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize session with attached databases
    session: AsyncSession = async_session_maker()  # type: ignore[assignment]
    await species_database.attach_all_to_session(session)

    # Create file manager
    file_manager = FileManager(path_resolver)

    # Create audio analysis service
    audio_analysis_service = AudioAnalysisManager(
        file_manager, path_resolver, config, species_database, session
    )

    return session, audio_analysis_service


async def async_main() -> None:
    """Async main function that runs in a single event loop."""
    # Configure structlog
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    configure_structlog(config)

    logger.info("Starting audio analysis wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifo)

    # Set up FIFO path
    fifo_base_path = path_resolver.get_fifo_base_path()
    DaemonState.fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")

    # Initialize session and service
    DaemonState.session, DaemonState.audio_analysis_service = await init_session_and_service(
        path_resolver, config
    )

    # Start the buffer flush task
    DaemonState.audio_analysis_service.start_buffer_flush_task()

    try:
        # Open FIFO for reading (non-blocking)
        DaemonState.fifo_analysis_fd = os.open(
            DaemonState.fifo_analysis_path, os.O_RDONLY | os.O_NONBLOCK
        )
        logger.info("Opened FIFO for reading: %s", DaemonState.fifo_analysis_path)

        # Main processing loop
        while not DaemonState.shutdown_flag:
            try:
                buffer_size = 4096  # Must match producer's write size
                audio_data_bytes = os.read(DaemonState.fifo_analysis_fd, buffer_size)

                if audio_data_bytes:
                    # Process audio chunk asynchronously without creating a new event loop
                    await DaemonState.audio_analysis_service.process_audio_chunk(audio_data_bytes)
                else:
                    # No data available, sleep briefly
                    await asyncio.sleep(0.01)

            except BlockingIOError:
                # No data available in non-blocking mode
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error("Error reading from FIFO: %s", e, exc_info=True)
                await asyncio.sleep(1)

    except FileNotFoundError:
        logger.error(
            "FIFO not found at %s. Ensure audio_capture is running and creating it.",
            DaemonState.fifo_analysis_path,
        )
    except Exception as e:
        logger.error("An error occurred in the audio analysis wrapper: %s", e, exc_info=True)


def main() -> None:
    """Run the audio analysis wrapper with a single persistent event loop."""
    # Create and run the event loop
    DaemonState.event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(DaemonState.event_loop)

    try:
        DaemonState.event_loop.run_until_complete(async_main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        _cleanup_fifo()


if __name__ == "__main__":
    main()
