import atexit
import logging
import os
import signal
import time

from birdnetpi.audio.audio_capture_service import AudioCaptureService
from birdnetpi.config import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

# Logger will be configured when main runs
logger = logging.getLogger(__name__)

_shutdown_flag = False
_fifo_analysis_path = None
_fifo_livestream_path = None
_fifo_analysis_fd = None
_fifo_livestream_fd = None


def _signal_handler(signum: int, frame: object) -> None:
    global _shutdown_flag
    signal_name = (
        signal.Signals(signum).name if signum in signal.Signals._value2member_map_ else str(signum)
    )
    logger.info("Signal %s (%s) received, initiating graceful shutdown...", signal_name, signum)
    _shutdown_flag = True


def _cleanup_fifos() -> None:
    global _fifo_analysis_fd, _fifo_livestream_fd, _fifo_analysis_path, _fifo_livestream_path
    if _fifo_analysis_fd:
        os.close(_fifo_analysis_fd)
        logger.info("Closed FIFO: %s", _fifo_analysis_path)
        _fifo_analysis_fd = None
    if _fifo_livestream_fd:
        os.close(_fifo_livestream_fd)
        logger.info("Closed FIFO: %s", _fifo_livestream_path)
        _fifo_livestream_fd = None
    if _fifo_analysis_path and os.path.exists(_fifo_analysis_path):
        pass  # os.unlink(_fifo_analysis_path) # Do not unlink, let readers reconnect
    if _fifo_livestream_path and os.path.exists(_fifo_livestream_path):
        pass  # os.unlink(_fifo_livestream_path) # Do not unlink, let readers reconnect


def main() -> None:
    """Run the audio capture wrapper."""
    global \
        _fifo_analysis_path, \
        _fifo_livestream_path, \
        _fifo_analysis_fd, \
        _fifo_livestream_fd, \
        _shutdown_flag

    # Configure structlog first thing in main
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    configure_structlog(config)

    logger.info("Starting audio capture wrapper.")

    # Register signal handlers and atexit for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup_fifos)

    fifo_base_path = path_resolver.get_fifo_base_path()

    _fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")
    _fifo_livestream_path = os.path.join(fifo_base_path, "birdnet_audio_livestream.fifo")

    audio_capture_service = None

    try:
        # Create named pipes
        os.makedirs(fifo_base_path, exist_ok=True)  # Ensure base path exists
        if not os.path.exists(_fifo_analysis_path):
            os.mkfifo(_fifo_analysis_path)
            logger.info("Created FIFO: %s", _fifo_analysis_path)
        if not os.path.exists(_fifo_livestream_path):
            os.mkfifo(_fifo_livestream_path)
            logger.info("Created FIFO: %s", _fifo_livestream_path)

        # Open FIFOs for writing
        _fifo_analysis_fd = os.open(_fifo_analysis_path, os.O_WRONLY)
        _fifo_livestream_fd = os.open(_fifo_livestream_path, os.O_WRONLY)
        logger.info("FIFOs opened for writing.")

        # Configuration already loaded above
        logger.info("Configuration loaded successfully.")

        # Instantiate and start the AudioCaptureService
        # Pass the file descriptors to the service
        audio_capture_service = AudioCaptureService(config, _fifo_analysis_fd, _fifo_livestream_fd)
        audio_capture_service.start_capture()
        logger.info("AudioCaptureService started.")

        while not _shutdown_flag:
            # Check if audio capture service requested shutdown (FIFO closed)
            if audio_capture_service and hasattr(audio_capture_service, "_shutdown_requested"):
                if audio_capture_service._shutdown_requested:
                    logger.info("Audio capture service detected FIFO closure, initiating shutdown")
                    break
            time.sleep(0.1)  # Check more frequently for responsive shutdown

    except FileNotFoundError:
        logger.exception("Configuration file not found")
    except Exception:
        logger.exception("An error occurred in the audio capture wrapper")
    finally:
        # Stop audio capture first (stops writing to FIFOs)
        if audio_capture_service:
            try:
                audio_capture_service.stop_capture()
                logger.info("AudioCaptureService stopped.")
            except Exception:
                logger.exception("Error stopping audio capture service")

        # Then cleanup FIFOs
        _cleanup_fifos()


if __name__ == "__main__":
    main()
