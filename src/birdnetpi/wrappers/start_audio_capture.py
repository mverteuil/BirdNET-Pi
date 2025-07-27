import logging
import time
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

def main():
    logger.info("Starting audio capture wrapper.")

    file_resolver = FilePathResolver()
    config_path = file_resolver.get_birdnet_pi_config_path()

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
        # In a real application, this would be managed by supervisord or similar
        while True:
            time.sleep(1) # Keep alive

    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}. Please ensure it exists.")
    except Exception as e:
        logger.error(f"An error occurred in the audio capture wrapper: {e}", exc_info=True)

if __name__ == "__main__":
    main()
