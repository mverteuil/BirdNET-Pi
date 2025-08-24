import datetime
import random
from datetime import UTC

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.web.models.detections import DetectionEvent


async def generate_dummy_detections(
    data_manager: DataManager, num_detections: int = 100, max_days_ago: int = 1
) -> None:
    """Generate and add dummy detection data to the database.

    Args:
        data_manager: DataManager instance for database operations
        num_detections: Number of detections to generate
        max_days_ago: Maximum days in the past for detections (0 = today only)
    """
    # Ensure database tables exist
    try:
        # This will create tables if they don't exist
        await data_manager.count_detections()
    except Exception:
        # If count fails, tables might not exist yet - that's okay
        pass

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
        # Generate timestamps with more weight on recent times
        if max_days_ago == 0:
            # All detections today
            days_ago = 0
        else:
            # Use exponential distribution to favor recent times
            days_ago = min(int(random.expovariate(1.0 / (max_days_ago / 3))), max_days_ago)

        timestamp = datetime.datetime.now(UTC) - datetime.timedelta(
            days=days_ago,
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )

        # Parse species components
        species_tensor = random.choice(species_list)
        scientific_name, common_name = species_tensor.split("_", 1)

        # Add random microseconds to ensure unique file paths
        unique_suffix = random.randint(0, 999999)

        detection_data = {
            "species_tensor": species_tensor,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "confidence": round(random.uniform(0.5, 0.99), 2),
            "timestamp": timestamp,
            "audio_file_path": (
                f"/app/audio/{timestamp.strftime('%Y%m%d_%H%M%S')}_{unique_suffix:06d}.wav"
            ),
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
        await data_manager.create_detection(detection_event)
    print(f"Generated {num_detections} dummy detections.")


if __name__ == "__main__":
    import asyncio

    from birdnetpi.config import ConfigManager
    from birdnetpi.database.database_service import DatabaseService
    from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
    from birdnetpi.species.display import SpeciesDisplayService
    from birdnetpi.system.path_resolver import PathResolver

    async def run() -> None:
        """Run the dummy data generator."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)
        config = config_manager.load()
        bnp_database_service = DatabaseService(path_resolver.get_database_path())
        multilingual_service = MultilingualDatabaseService(path_resolver)
        species_display_service = SpeciesDisplayService(config)
        data_manager = DataManager(
            bnp_database_service, multilingual_service, species_display_service
        )
        await generate_dummy_detections(data_manager)

    asyncio.run(run())
