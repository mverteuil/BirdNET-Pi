import logging
import time
import signal
from multiprocessing import Queue

from birdnetpi.services.audio_capture_service import AudioCaptureService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure logging for this script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_shutdown_flag = False

def _signal_handler(signum, frame):
    global _shutdown_flag
    logger.info(f"Signal {signum} received, initiating graceful shutdown...")
    _shutdown_flag = True

def main():
    logger.info("Starting audio capture wrapper.")

    # Register signal handlers
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    file_resolver = FilePathResolver()
    config_path = file_resolver.get_birdnet_pi_config_path()

    audio_capture_service = None # Initialize to None

    try:
        # Load configuration
        config_parser = ConfigFileParser(config_path)
        config = config_parser.load_config()
        logger.info("Configuration loaded successfully.")

        # Create a multiprocessing queue
        audio_queue = Queue()

        # Instantiate and start the AudioCaptureService
        audio_capture_service = AudioCaptureService(config, audio_queue)
        audio_capture_service.start_capture()
        logger.info("AudioCaptureService started.")

        # Keep the main process alive to allow the audio stream to run
        while not _shutdown_flag:
            time.sleep(1) # Keep alive

    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}. Please ensure it exists.")
    except Exception as e:
        logger.error(f"An error occurred in the audio capture wrapper: {e}", exc_info=True)
    finally:
        if audio_capture_service:
            audio_capture_service.stop_capture()
            logger.info("AudioCaptureService stopped.")

if __name__ == "__main__":
    main()
