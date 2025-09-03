import asyncio
import os
import time

import click

from birdnetpi.config import ConfigManager
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.utils.dummy_data_generator import generate_dummy_detections


async def run(count: int = 100, days: int = 3) -> None:
    """Generate dummy data for the application."""
    path_resolver = PathResolver()
    db_path = path_resolver.get_database_path()

    # Initialize system control service
    system_control = SystemControlService()

    # Determine the FastAPI service name based on environment
    fastapi_service_name = _get_fastapi_service_name()

    # Load configuration for services
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()

    # Check if database exists
    if db_path.exists() and db_path.stat().st_size > 0:
        print(f"Database file exists and is {db_path.stat().st_size} bytes.")
        try:
            bnp_database_service = DatabaseService(db_path)
            multilingual_service = SpeciesDatabaseService(path_resolver)
            species_display_service = SpeciesDisplayService(config)
            file_manager = FileManager(path_resolver)
            data_manager = DataManager(
                bnp_database_service,
                multilingual_service,
                species_display_service,
                file_manager,
                path_resolver,
            )
            detections = await data_manager.get_all_detections()
            if detections:
                print(f"Database already contains {len(detections)} detections.")
                print("Adding more dummy data...")
        except Exception as e:
            print(f"Warning: Could not check existing data due to database lock: {e}")
            print("Database appears to be in use. Attempting to stop services automatically...")
            # Continue to service management instead of exiting early
    else:
        print("Database is empty or does not exist. Generating dummy data...")

    # Check if FastAPI is running
    fastapi_was_running = False
    try:
        status = system_control.get_service_status(fastapi_service_name)
        fastapi_was_running = status == "active"
        if fastapi_was_running:
            print(
                f"FastAPI service ({fastapi_service_name}) is running. Stopping it temporarily..."
            )
            system_control.stop_service(fastapi_service_name)
            # Wait a moment for the service to stop and release database locks
            time.sleep(3)
    except Exception as e:
        print(f"Warning: Could not check FastAPI service status: {e}")
        print("Proceeding with dummy data generation...")

    try:
        # Generate dummy data with exclusive database access
        print("Generating dummy data...")
        bnp_database_service = DatabaseService(db_path)
        multilingual_service = SpeciesDatabaseService(path_resolver)
        species_display_service = SpeciesDisplayService(config)
        file_manager = FileManager(path_resolver)
        data_manager = DataManager(
            bnp_database_service,
            multilingual_service,
            species_display_service,
            file_manager,
            path_resolver,
        )
        await generate_dummy_detections(data_manager, num_detections=count, max_days_ago=days)
        print(f"Dummy data generation complete. Generated {count} detections.")

    finally:
        # Restart FastAPI if it was running before
        if fastapi_was_running:
            print(f"Restarting FastAPI service ({fastapi_service_name})...")
            try:
                system_control.start_service(fastapi_service_name)
                print("FastAPI service restarted successfully.")
            except Exception as e:
                print(f"Warning: Could not restart FastAPI service: {e}")
                print("You may need to manually restart the service.")


def _get_fastapi_service_name() -> str:
    """Determine the FastAPI service name based on the environment."""
    # Check if we're in a Docker container
    if os.getenv("DOCKER_CONTAINER", "false").lower() == "true" or os.path.exists("/.dockerenv"):
        # In Docker, FastAPI might be managed by supervisord
        return "fastapi"  # This would be the supervisor program name
    else:
        # On SBC/systemd, it might be a systemd service
        return "birdnetpi-fastapi"  # Common systemd service name pattern


@click.command()
@click.option(
    "--count", "-n", default=100, type=int, help="Number of detections to generate (default: 100)"
)
@click.option(
    "--days",
    "-d",
    default=1,
    type=int,
    help="Maximum days in the past for detections (0=today only, default: 1)",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def main(count: int, days: int, verbose: bool) -> None:
    """Generate dummy detection data for testing BirdNET-Pi.

    This command creates realistic bird detection data for testing and development.
    By default, it generates 100 detections within the last 24 hours.

    Examples:
        # Generate 100 detections from today only
        generate-dummy-data --days 0

        # Generate 500 detections from the last week
        generate-dummy-data --count 500 --days 7

        # Generate 50 detections from the last 24 hours (default)
        generate-dummy-data --count 50
    """
    if verbose:
        print(f"Generating {count} detections from the last {days} day(s)...")

    asyncio.run(run(count, days))


if __name__ == "__main__":
    main()
