import datetime
import random
from datetime import UTC

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.models import DetectionEvent


def generate_dummy_detections(data_manager: DataManager, num_detections: int = 100) -> None:
    """Generate and add dummy detection data to the database."""
    # Updated to use tensor format: "Scientific_name_Common Name"
    species_list = [
        "Turdus migratorius_American Robin",
        "Cardinalis cardinalis_Northern Cardinal",
        "Cyanocitta cristata_Blue Jay",
        "Passer domesticus_House Sparrow",
        "Sturnus vulgaris_European Starling",
        "Quiscalus quiscula_Common Grackle",
        "Zenaida macroura_Mourning Dove",
        "Dryobates pubescens_Downy Woodpecker",
        "Melospiza melodia_Song Sparrow",
        "Agelaius phoeniceus_Red-winged Blackbird",
    ]

    for _ in range(num_detections):
        timestamp = datetime.datetime.now(UTC) - datetime.timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )

        # Parse species components
        species_tensor = random.choice(species_list)
        scientific_name, common_name = species_tensor.split("_", 1)

        detection_data = {
            "species_tensor": species_tensor,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "confidence": round(random.uniform(0.5, 0.99), 2),
            "timestamp": timestamp,
            "audio_file_path": f"/app/audio/{timestamp.strftime('%Y%m%d_%H%M%S')}.wav",
            "latitude": round(random.uniform(30.0, 40.0), 4),
            "longitude": round(random.uniform(-80.0, -70.0), 4),
            "species_confidence_threshold": random.uniform(0.1, 0.5),
            "week": timestamp.isocalendar()[1],
            "sensitivity_setting": random.uniform(0.5, 0.9),
            "overlap": random.uniform(0.0, 0.5),
            "duration": 5.0,  # Added for DetectionEvent
            "size_bytes": 1024,  # Added for DetectionEvent
        }
        # Convert dict to DetectionEvent object
        detection_event = DetectionEvent(**detection_data)
        data_manager.create_detection(detection_event)
    print(f"Generated {num_detections} dummy detections.")


if __name__ == "__main__":
    from birdnetpi.config import ConfigManager
    from birdnetpi.database.database_service import DatabaseService
    from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
    from birdnetpi.species.species_display_service import SpeciesDisplayService
    from birdnetpi.system.path_resolver import PathResolver

    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()
    bnp_database_service = DatabaseService(path_resolver.get_database_path())
    multilingual_service = MultilingualDatabaseService(path_resolver)
    species_display_service = SpeciesDisplayService(config)
    data_manager = DataManager(bnp_database_service, multilingual_service, species_display_service)

    generate_dummy_detections(data_manager)
