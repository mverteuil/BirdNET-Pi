import atexit
import logging
import os
import signal
import time

from birdnetpi.audio.audio_capture_service import AudioCaptureService
from birdnetpi.config import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog

logger = logging.getLogger(__name__)


class DaemonState:
    """Encapsulates daemon state to avoid module-level globals."""

    shutdown_flag: bool = False
    fifo_analysis_path: str | None = None
    fifo_livestream_path: str | None = None
    fifo_analysis_fd: int | None = None
    fifo_livestream_fd: int | None = None

    @classmethod
    def reset(cls) -> None:
        """Reset state to initial values (useful for testing)."""
        cls.shutdown_flag = False
        cls.fifo_analysis_path = None
        cls.fifo_livestream_path = None
        cls.fifo_analysis_fd = None
        cls.fifo_livestream_fd = None


def _signal_handler(signum: int, frame: object) -> None:
    signal_name = (
        signal.Signals(signum).name if signum in signal.Signals._value2member_map_ else str(signum)
    )
    logger.info("Signal %s (%s) received, initiating graceful shutdown...", signal_name, signum)
    DaemonState.shutdown_flag = True


def _cleanup_fifos() -> None:
    if DaemonState.fifo_analysis_fd:
        os.close(DaemonState.fifo_analysis_fd)
        logger.info("Closed FIFO: %s", DaemonState.fifo_analysis_path)
        DaemonState.fifo_analysis_fd = None
    if DaemonState.fifo_livestream_fd:
        os.close(DaemonState.fifo_livestream_fd)
        logger.info("Closed FIFO: %s", DaemonState.fifo_livestream_path)
        DaemonState.fifo_livestream_fd = None
    if DaemonState.fifo_analysis_path and os.path.exists(DaemonState.fifo_analysis_path):
        pass  # os.unlink(DaemonState.fifo_analysis_path) # Do not unlink, let readers reconnect
    if DaemonState.fifo_livestream_path and os.path.exists(DaemonState.fifo_livestream_path):
        pass  # os.unlink(DaemonState.fifo_livestream_path) # Do not unlink, let readers reconnect


def main() -> None:
    """Run the audio capture wrapper."""
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

    DaemonState.fifo_analysis_path = os.path.join(fifo_base_path, "birdnet_audio_analysis.fifo")
    DaemonState.fifo_livestream_path = os.path.join(fifo_base_path, "birdnet_audio_livestream.fifo")

    audio_capture_service = None

    try:
        # Create named pipes
        os.makedirs(fifo_base_path, exist_ok=True)  # Ensure base path exists
        if not os.path.exists(DaemonState.fifo_analysis_path):
            os.mkfifo(DaemonState.fifo_analysis_path)
            logger.info("Created FIFO: %s", DaemonState.fifo_analysis_path)
        if not os.path.exists(DaemonState.fifo_livestream_path):
            os.mkfifo(DaemonState.fifo_livestream_path)
            logger.info("Created FIFO: %s", DaemonState.fifo_livestream_path)

        # Open FIFOs for writing
        DaemonState.fifo_analysis_fd = os.open(DaemonState.fifo_analysis_path, os.O_WRONLY)
        DaemonState.fifo_livestream_fd = os.open(DaemonState.fifo_livestream_path, os.O_WRONLY)
        logger.info("FIFOs opened for writing.")

        # Configuration already loaded above
        logger.info("Configuration loaded successfully.")

        # Instantiate and start the AudioCaptureService
        # Pass the file descriptors to the service
        audio_capture_service = AudioCaptureService(
            config, DaemonState.fifo_analysis_fd, DaemonState.fifo_livestream_fd
        )
        audio_capture_service.start_capture()
        logger.info("AudioCaptureService started.")

        while not DaemonState.shutdown_flag:
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
        try:
            if audio_capture_service is not None:
                audio_capture_service.stop_capture()
                logger.info("AudioCaptureService stopped.")
        except Exception:
            logger.exception("Error stopping audio capture service")

        # Then cleanup FIFOs
        _cleanup_fifos()


if __name__ == "__main__":
    main()
