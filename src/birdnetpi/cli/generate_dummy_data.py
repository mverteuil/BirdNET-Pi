import os
import time

from birdnetpi.config import ConfigManager
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.dummy_data_generator import generate_dummy_detections
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.species.species_display_service import SpeciesDisplayService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control_service import SystemControlService


def main() -> None:
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

    # Check if database already has data
    if db_path.exists() and db_path.stat().st_size > 0:
        print(f"Database file exists and is {db_path.stat().st_size} bytes.")
        try:
            bnp_database_service = DatabaseService(db_path)
            multilingual_service = MultilingualDatabaseService(path_resolver)
            species_display_service = SpeciesDisplayService(config)
            data_manager = DataManager(
                bnp_database_service, multilingual_service, species_display_service
            )
            if data_manager.get_all_detections():
                print("Database already contains data. Skipping dummy data generation.")
                return
        except Exception as e:
            print(f"Warning: Could not check existing data due to database lock: {e}")
            print("Database appears to be in use. Attempting to stop services automatically...")
            # Continue to service management instead of exiting early

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
        print("Database is empty or does not exist. Generating dummy data...")
        bnp_database_service = DatabaseService(db_path)
        multilingual_service = MultilingualDatabaseService(path_resolver)
        species_display_service = SpeciesDisplayService(config)
        data_manager = DataManager(
            bnp_database_service, multilingual_service, species_display_service
        )
        generate_dummy_detections(data_manager)
        print("Dummy data generation complete.")

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


if __name__ == "__main__":
    main()
