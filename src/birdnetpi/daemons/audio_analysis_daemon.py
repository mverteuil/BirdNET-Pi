import asyncio
import atexit
import logging
import os
import signal
import time
from types import FrameType
from typing import TYPE_CHECKING

from birdnetpi.audio.audio_analysis_manager import AudioAnalysisManager
from birdnetpi.config import ConfigManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from birdnetpi.config import BirdNETConfig

# Logger will be configured when main runs
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_analysis_path = None
_fifo_analysis_fd = None
_session = None
_event_loop = None  # Persistent event loop


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo() -> None:
    global _fifo_analysis_fd, _fifo_analysis_path, _session, _audio_analysis_service, _event_loop

    # Stop audio analysis manager first to ensure no ongoing processing
    if "_audio_analysis_service" in globals() and _audio_analysis_service:
        try:
            _audio_analysis_service.stop_buffer_flush_task()
            logger.info("Stopped audio analysis buffer flush task")
            # Give a moment for threads to finish
            time.sleep(0.2)
        except Exception as e:
            logger.debug("Error stopping buffer flush task: %s", e)

    # Close FIFO
    if _fifo_analysis_fd:
        os.close(_fifo_analysis_fd)
        logger.info("Closed FIFO: %s", _fifo_analysis_path)
        _fifo_analysis_fd = None

    # Clean up database session and event loop
    if _event_loop and not _event_loop.is_closed():
        if "_session" in globals() and _session:
            try:
                _event_loop.run_until_complete(_session.close())
            except Exception as e:
                logger.debug("Error closing session: %s", e)
        _event_loop.close()


async def init_session_and_service(
    path_resolver: PathResolver, config: "BirdNETConfig"
) -> tuple["AsyncSession", AudioAnalysisManager]:
    """Initialize async session and audio analysis service."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService

    # Create multilingual database service
    multilingual_service = MultilingualDatabaseService(path_resolver)
    logger.info("Multilingual database service initialized")

    # Create async session for database queries
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize session with attached databases
    session: AsyncSession = async_session_maker()  # type: ignore[assignment]
    await multilingual_service.attach_all_to_session(session)

    # Create file manager
    file_manager = FileManager(path_resolver)

    # Create audio analysis service
    audio_analysis_service = AudioAnalysisManager(
        file_manager, path_resolver, config, multilingual_service, session
    )

    return session, audio_analysis_service


async def async_main() -> None:
    """Async main function that runs in a single event loop."""
    global _fifo_analysis_path, _fifo_analysis_fd, _session, _audio_analysis_service

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
    _fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")

    # Initialize session and service
    _session, _audio_analysis_service = await init_session_and_service(path_resolver, config)

    # Start the buffer flush task
    _audio_analysis_service.start_buffer_flush_task()

    try:
        # Open FIFO for reading (non-blocking)
        _fifo_analysis_fd = os.open(_fifo_analysis_path, os.O_RDONLY | os.O_NONBLOCK)
        logger.info("Opened FIFO for reading: %s", _fifo_analysis_path)

        # Main processing loop
        while not _shutdown_flag:
            try:
                buffer_size = 4096  # Must match producer's write size
                audio_data_bytes = os.read(_fifo_analysis_fd, buffer_size)

                if audio_data_bytes:
                    # Process audio chunk asynchronously without creating a new event loop
                    await _audio_analysis_service.process_audio_chunk(audio_data_bytes)
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
            _fifo_analysis_path,
        )
    except Exception as e:
        logger.error("An error occurred in the audio analysis wrapper: %s", e, exc_info=True)


def main() -> None:
    """Run the audio analysis wrapper with a single persistent event loop."""
    global _event_loop

    # Create and run the event loop
    _event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_event_loop)

    try:
        _event_loop.run_until_complete(async_main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        _cleanup_fifo()


if __name__ == "__main__":
    main()
