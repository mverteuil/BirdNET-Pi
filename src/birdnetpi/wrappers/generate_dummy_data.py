import os

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.dummy_data_generator import generate_dummy_detections
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main() -> None:
    """Generate dummy data for the application."""
    file_resolver = FilePathResolver()
    config_parser = ConfigFileParser(file_resolver.get_birdnet_pi_config_path())
    config = config_parser.load_config()
    db_path = config.data.db_path

    # Check if the database file exists and has data
    if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
        db_service = DatabaseService(db_path)
        detection_manager = DetectionManager(db_service)
        if detection_manager.get_all_detections():
            print("Database already contains data. Skipping dummy data generation.")
            return

    # If database is empty or doesn't exist, generate dummy data
    print("Database is empty or does not exist. Generating dummy data...")
    db_service = DatabaseService(db_path)
    detection_manager = DetectionManager(db_service)
    generate_dummy_detections(detection_manager)
    print("Dummy data generation complete.")


if __name__ == "__main__":
    main()
