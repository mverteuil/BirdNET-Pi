import datetime
import random
from datetime import UTC

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.models.detections import DetectionEvent


async def get_random_ioc_species(
    path_resolver: PathResolver, num_species: int = 10
) -> list[tuple[str, str]]:
    """Get random species from the IOC database.

    Args:
        path_resolver: PathResolver instance to get database path
        num_species: Number of random species to retrieve

    Returns:
        List of tuples (scientific_name, common_name)
    """
    import aiosqlite

    # Query the IOC database for random species
    ioc_db_path = path_resolver.get_ioc_database_path()

    async with aiosqlite.connect(ioc_db_path) as db:
        cursor = await db.execute(
            """
            SELECT scientific_name, english_name
            FROM species
            WHERE english_name IS NOT NULL
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (num_species,),
        )
        results = await cursor.fetchall()
        return [(row[0], row[1]) for row in results]


async def generate_dummy_detections(
    data_manager: DataManager,
    num_detections: int = 100,
    max_days_ago: int = 1,
    ioc_species_ratio: float = 0.2,
) -> None:
    """Generate and add dummy detection data to the database.

    Args:
        data_manager: DataManager instance for database operations
        num_detections: Number of detections to generate
        max_days_ago: Maximum days in the past for detections (0 = today only)
        ioc_species_ratio: Ratio of IOC species as infrequent visitors (0 = disabled, 0.2 = 20%)
    """
    # Database tables will be created automatically when we create the first detection

    # Common species - these appear frequently
    common_species = [
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

    # Get random IOC species as infrequent visitors if enabled
    ioc_species = []
    if ioc_species_ratio > 0 and hasattr(data_manager, "path_resolver"):
        try:
            # Get 20 random species from IOC database
            ioc_results = await get_random_ioc_species(data_manager.path_resolver, 20)
            # Format as tensor strings
            ioc_species = [f"{sci}_{com}" for sci, com in ioc_results]
            print(f"Loaded {len(ioc_species)} random IOC species as infrequent visitors")
        except Exception as e:
            print(f"Could not fetch IOC species: {e}")
            ioc_species = []
            ioc_species_ratio = 0  # Disable if we couldn't load species

    for i in range(num_detections):
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
            # Add microseconds to ensure uniqueness for same species/second combinations
            microseconds=i * 1000,  # Increment by 1ms per detection
        )

        # Select species based on ratio
        # IOC species are infrequent visitors
        if ioc_species and random.random() < ioc_species_ratio:
            # Select an IOC species (infrequent visitor)
            species_tensor = random.choice(ioc_species)
        else:
            # Select a common species
            species_tensor = random.choice(common_species)

        # Parse species components
        scientific_name, common_name = species_tensor.split("_", 1)

        # Generate dummy audio data (base64 encoded)
        import base64

        dummy_audio = b"\x00" * 1024  # 1KB of null bytes as dummy audio
        audio_data_base64 = base64.b64encode(dummy_audio).decode("utf-8")

        detection_data = {
            "species_tensor": species_tensor,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "confidence": round(random.uniform(0.5, 0.99), 2),
            "timestamp": timestamp,
            "audio_data": audio_data_base64,  # Base64-encoded audio
            "sample_rate": 48000,  # Standard sample rate
            "channels": 1,  # Mono audio
            "latitude": round(random.uniform(30.0, 40.0), 4),
            "longitude": round(random.uniform(-80.0, -70.0), 4),
            "species_confidence_threshold": random.uniform(0.1, 0.5),
            "week": timestamp.isocalendar()[1],
            "sensitivity_setting": random.uniform(0.5, 0.9),
            "overlap": random.uniform(0.0, 0.5),
        }
        # Convert dict to DetectionEvent object
        detection_event = DetectionEvent(**detection_data)
        await data_manager.create_detection(detection_event)
    print(f"Generated {num_detections} dummy detections.")


if __name__ == "__main__":
    import asyncio

    from birdnetpi.config import ConfigManager
    from birdnetpi.species.display import SpeciesDisplayService
    from birdnetpi.system.file_manager import FileManager
    from birdnetpi.system.path_resolver import PathResolver

    async def run() -> None:
        """Run the dummy data generator."""
        path_resolver = PathResolver()
        config_manager = ConfigManager(path_resolver)
        config = config_manager.load()
        core_database = CoreDatabaseService(path_resolver.get_database_path())
        species_database = SpeciesDatabaseService(path_resolver)
        species_display_service = SpeciesDisplayService(config)
        file_manager = FileManager(path_resolver)
        data_manager = DataManager(
            core_database,
            species_database,
            species_display_service,
            file_manager,
            path_resolver,
        )
        await generate_dummy_detections(data_manager)

    asyncio.run(run())
