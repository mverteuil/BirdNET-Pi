import atexit
import logging
import os
import signal
import time
from types import FrameType

from birdnetpi.services.audio_livestream_service import AudioLivestreamService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_livestream_path = None
_fifo_livestream_fd = None
_audio_livestream_service = None


def _signal_handler(signum: int, frame: FrameType) -> None:
    global _shutdown_flag
    logger.info("Signal %s received, initiating graceful shutdown...", signum)
    _shutdown_flag = True


def _cleanup_fifo_and_service() -> None:
    global _fifo_livestream_fd, _fifo_livestream_path, _audio_livestream_service
    if _fifo_livestream_fd:
        os.close(_fifo_livestream_fd)
        logger.info("Closed FIFO: %s", _fifo_livestream_path)
    if _audio_livestream_service:
        _audio_livestream_service.stop_livestream()


def main() -> None:
    """Run the audio livestream wrapper."""
    global _fifo_livestream_path, _fifo_livestream_fd, _audio_livestream_service
    logger.info("Starting audio livestream wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifo_and_service)

    file_resolver = FilePathResolver()
    fifo_base_path = file_resolver.get_fifo_base_path()
    _fifo_livestream_path = os.path.join(fifo_base_path, "birdnet_audio_livestream.fifo")

    try:
        # Load configuration
        config_path = file_resolver.get_birdnet_pi_config_path()
        config_parser = ConfigFileParser(config_path)
        config = config_parser.load_config()
        logger.info("Configuration loaded successfully.")

        # Open FIFO for reading
        _fifo_livestream_fd = os.open(_fifo_livestream_path, os.O_RDONLY | os.O_NONBLOCK)
        logger.info("Opened FIFO for reading: %s", _fifo_livestream_path)

        # Instantiate and start the AudioLivestreamService
        icecast_url = "icecast://source:hackme@icecast:8000/stream.mp3"  # TODO: Make configurable
        samplerate = config.sample_rate
        channels = config.audio_channels

        _audio_livestream_service = AudioLivestreamService(icecast_url, samplerate, channels)
        _audio_livestream_service.start_livestream()

        # Read from FIFO and write to FFmpeg's stdin via the service
        while not _shutdown_flag:
            try:
                buffer_size = 4096  # Must match producer's write size
                audio_data_bytes = os.read(_fifo_livestream_fd, buffer_size)

                if audio_data_bytes:
                    _audio_livestream_service.stream_audio_chunk(audio_data_bytes)
                else:
                    time.sleep(0.01)

            except BlockingIOError:
                time.sleep(0.01)
            except Exception as e:
                logger.error("Error reading from FIFO or streaming audio: %s", e, exc_info=True)
                time.sleep(1)

    except FileNotFoundError:
        logger.error(
            "FIFO not found at %s. Ensure audio_capture is running and creating it.",
            _fifo_livestream_path,
        )
    except Exception as e:
        logger.error("An error occurred in the audio livestream wrapper: %s", e, exc_info=True)
    finally:
        _cleanup_fifo_and_service()


if __name__ == "__main__":
    main()
