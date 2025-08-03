import datetime
import random

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.detection_event import DetectionEvent


def generate_dummy_detections(
    detection_manager: DetectionManager, num_detections: int = 100
) -> None:
    """Generate and add dummy detection data to the database."""
    species_list = [
        "American Robin (Turdus migratorius)",
        "Northern Cardinal (Cardinalis cardinalis)",
        "Blue Jay (Cyanocitta cristata)",
        "House Sparrow (Passer domesticus)",
        "European Starling (Sturnus vulgaris)",
        "Common Grackle (Quiscalus quiscula)",
        "Mourning Dove (Zenaida macroura)",
        "Downy Woodpecker (Dryobates pubescens)",
        "Song Sparrow (Melospiza melodia)",
        "Red-winged Blackbird (Agelaius phoeniceus)",
    ]

    for _ in range(num_detections):
        timestamp = datetime.datetime.now() - datetime.timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )
        detection_data = {
            "species": random.choice(species_list),
            "confidence": round(random.uniform(0.5, 0.99), 2),
            "timestamp": timestamp,
            "audio_file_path": f"/app/audio/{timestamp.strftime('%Y%m%d_%H%M%S')}.wav",
            "latitude": round(random.uniform(30.0, 40.0), 4),
            "longitude": round(random.uniform(-80.0, -70.0), 4),
            "cutoff": random.uniform(0.1, 0.5),
            "week": timestamp.isocalendar()[1],
            "sensitivity": random.uniform(0.5, 0.9),
            "overlap": random.uniform(0.0, 0.5),
            "is_extracted": False,
            "duration": 5.0,  # Added for DetectionEvent
            "size_bytes": 1024,  # Added for DetectionEvent
            "recording_start_time": timestamp,  # Added for DetectionEvent
        }
        # Convert dict to DetectionEvent object
        detection_event = DetectionEvent(**detection_data)
        detection_manager.create_detection(detection_event)
    print(f"Generated {num_detections} dummy detections.")


if __name__ == "__main__":
    from birdnetpi.services.database_service import DatabaseService
    from birdnetpi.utils.config_file_parser import ConfigFileParser
    from birdnetpi.utils.file_path_resolver import FilePathResolver

    file_resolver = FilePathResolver()
    config_parser = ConfigFileParser(file_resolver.get_birdnetpi_config_path())
    config = config_parser.load_config()
    db_service = DatabaseService(file_resolver.get_database_path())
    detection_manager = DetectionManager(db_service)

    generate_dummy_detections(detection_manager)
