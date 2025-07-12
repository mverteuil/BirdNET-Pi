import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.data_manager import DataManager
from services.file_manager import FileManager
from utils.config_file_parser import ConfigFileParser

if __name__ == "__main__":
    # This is a placeholder for where the config would be loaded
    # In a real application, this would be handled by a config loader
    config = ConfigFileParser("etc/birdnet.conf").parse()

    file_manager = FileManager(config.data.recordings_dir)

    data_manager = DataManager(config, file_manager)
    data_manager.cleanup_processed_files()
