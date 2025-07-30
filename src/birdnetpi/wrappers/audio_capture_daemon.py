import atexit
import logging
import os
import signal
import time

from birdnetpi.services.audio_capture_service import AudioCaptureService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_analysis_path = None
_fifo_livestream_path = None
_fifo_analysis_fd = None
_fifo_livestream_fd = None


def _signal_handler(signum: int, frame: object) -> None:
    global _shutdown_flag
    logger.info(f"Signal {signum} received, initiating graceful shutdown...")
    _shutdown_flag = True


def _cleanup_fifos() -> None:
    global _fifo_analysis_fd, _fifo_livestream_fd, _fifo_analysis_path, _fifo_livestream_path
    if _fifo_analysis_fd:
        os.close(_fifo_analysis_fd)
        logger.info(f"Closed FIFO: {_fifo_analysis_path}")
        _fifo_analysis_fd = None
    if _fifo_livestream_fd:
        os.close(_fifo_livestream_fd)
        logger.info(f"Closed FIFO: {_fifo_livestream_path}")
        _fifo_livestream_fd = None
    if _fifo_analysis_path and os.path.exists(_fifo_analysis_path):
        pass  # os.unlink(_fifo_analysis_path) # Do not unlink, let readers reconnect
    if _fifo_livestream_path and os.path.exists(_fifo_livestream_path):
        pass  # os.unlink(_fifo_livestream_path) # Do not unlink, let readers reconnect


def main() -> None:
    """Run the audio capture wrapper."""
    global _fifo_analysis_path, _fifo_livestream_path, _fifo_analysis_fd, _fifo_livestream_fd
    logger.info("Starting audio capture wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifos)

    file_resolver = FilePathResolver()
    config_path = file_resolver.get_birdnet_pi_config_path()
    fifo_base_path = file_resolver.get_fifo_base_path()

    _fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")
    _fifo_livestream_path = os.path.join(fifo_base_path, "birdnet_audio_livestream.fifo")

    audio_capture_service = None

    try:
        # Create named pipes
        os.makedirs(fifo_base_path, exist_ok=True)  # Ensure base path exists
        if not os.path.exists(_fifo_analysis_path):
            os.mkfifo(_fifo_analysis_path)
            logger.info(f"Created FIFO: {_fifo_analysis_path}")
        if not os.path.exists(_fifo_livestream_path):
            os.mkfifo(_fifo_livestream_path)
            logger.info(f"Created FIFO: {_fifo_livestream_path}")

        # Open FIFOs for writing
        _fifo_analysis_fd = os.open(_fifo_analysis_path, os.O_WRONLY)
        _fifo_livestream_fd = os.open(_fifo_livestream_path, os.O_WRONLY)
        logger.info("FIFOs opened for writing.")

        # Load configuration
        config_parser = ConfigFileParser(config_path)
        config = config_parser.load_config()
        logger.info("Configuration loaded successfully.")

        # Instantiate and start the AudioCaptureService
        # Pass the file descriptors to the service
        audio_capture_service = AudioCaptureService(config, _fifo_analysis_fd, _fifo_livestream_fd)
        audio_capture_service.start_capture()
        logger.info("AudioCaptureService started.")

        while not _shutdown_flag:
            time.sleep(1)

    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}. Please ensure it exists.")
    except Exception as e:
        logger.error(f"An error occurred in the audio capture wrapper: {e}", exc_info=True)
    finally:
        if audio_capture_service:
            audio_capture_service.stop_capture()
            logger.info("AudioCaptureService stopped.")
        _cleanup_fifos()


if __name__ == "__main__":
    main()
