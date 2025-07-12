import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.audio_manager import AudioManager
from utils.config_file_parser import ConfigFileParser

if __name__ == "__main__":
    # This is a placeholder for where the config would be loaded
    # In a real application, this would be handled by a config loader
    config = ConfigFileParser("etc/birdnet.conf").parse()

    audio_manager = AudioManager(config)
    audio_manager.record()
