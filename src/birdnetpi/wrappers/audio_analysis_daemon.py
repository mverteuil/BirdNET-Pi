import asyncio
import atexit
import logging
import os
import signal
import time
from types import FrameType

from birdnetpi.managers.audio_analysis_manager import AudioAnalysisManager
from birdnetpi.managers.file_manager import FileManager
from birdnetpi.services.ioc_database_service import IOCDatabaseService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_analysis_path = None
_fifo_analysis_fd = None


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo() -> None:
    global _fifo_analysis_fd, _fifo_analysis_path
    if _fifo_analysis_fd:
        os.close(_fifo_analysis_fd)
        logger.info("Closed FIFO: %s", _fifo_analysis_path)
        _fifo_analysis_fd = None


def main() -> None:
    """Run the audio analysis wrapper."""
    global _fifo_analysis_path, _fifo_analysis_fd
    logger.info("Starting audio analysis wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifo)

    file_resolver = FilePathResolver()
    fifo_base_path = file_resolver.get_fifo_base_path()
    _fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")

    file_manager = FileManager(file_resolver)
    config_parser = ConfigFileParser(file_resolver.get_birdnetpi_config_path())
    config = config_parser.load_config()

    # Create IOC database service with graceful error handling
    ioc_database_service = None
    try:
        ioc_database_service = IOCDatabaseService(file_resolver.get_ioc_database_path())
        logger.info("IOC database service initialized")
    except Exception as e:
        logger.warning("IOC database service not available: %s", e)

    audio_analysis_service = AudioAnalysisManager(
        file_manager, file_resolver, config, ioc_database_service=ioc_database_service
    )

    try:
        # Open FIFO for reading
        _fifo_analysis_fd = os.open(_fifo_analysis_path, os.O_RDONLY | os.O_NONBLOCK)
        logger.info("Opened FIFO for reading: %s", _fifo_analysis_path)

        while not _shutdown_flag:
            try:
                buffer_size = 4096  # Must match producer's write size
                audio_data_bytes = os.read(_fifo_analysis_fd, buffer_size)

                if audio_data_bytes:
                    asyncio.run(audio_analysis_service.process_audio_chunk(audio_data_bytes))
                else:
                    time.sleep(0.01)

            except BlockingIOError:
                time.sleep(0.01)
            except Exception as e:
                logger.error("Error reading from FIFO: %s", e, exc_info=True)
                time.sleep(1)

    except FileNotFoundError:
        logger.error(
            "FIFO not found at %s. Ensure audio_capture is running and creating it.",
            _fifo_analysis_path,
        )
    except Exception as e:
        logger.error("An error occurred in the audio analysis wrapper: %s", e, exc_info=True)
    finally:
        _cleanup_fifo()


if __name__ == "__main__":
    main()
