
from .managers.data_manager import DataManager
from .services.database_manager import DatabaseManager
from .services.file_manager import FileManager
from .utils.config_file_parser import ConfigFileParser

if __name__ == "__main__":
    # This is a placeholder for where the config would be loaded
    # In a real application, this would be handled by a config loader
    config = ConfigFileParser("etc/birdnet.conf").parse()

    file_manager = FileManager(config.data.recordings_dir)
    database_manager = DatabaseManager(config.data.db_path)
    database_manager.initialize_database()

    data_manager = DataManager(config, file_manager, database_manager)
    data_manager.clear_all_data()
