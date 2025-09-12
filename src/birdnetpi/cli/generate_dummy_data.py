import asyncio
import os
import time

import click

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.manager import DataManager
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.utils.dummy_data_generator import generate_dummy_detections


async def run(count: int = 100, days: int = 3, ioc_species_ratio: float = 0.2) -> None:
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
        click.echo(f"Database file exists and is {db_path.stat().st_size} bytes.")
        try:
            core_database = CoreDatabaseService(db_path)
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
            detections = await data_manager.get_all_detections()
            if detections:
                click.echo(f"Database already contains {len(detections)} detections.")
                click.echo("Adding more dummy data...")
        except Exception as e:
            click.echo(
                click.style(
                    f"Warning: Could not check existing data due to database lock: {e}", fg="yellow"
                )
            )
            click.echo(
                "Database appears to be in use. Attempting to stop services automatically..."
            )
            # Continue to service management instead of exiting early
    else:
        click.echo("Database is empty or does not exist. Generating dummy data...")

    # Check if FastAPI is running
    fastapi_was_running = False
    try:
        status = system_control.get_service_status(fastapi_service_name)
        fastapi_was_running = status == "active"
        if fastapi_was_running:
            click.echo(
                f"FastAPI service ({fastapi_service_name}) is running. Stopping it temporarily..."
            )
            system_control.stop_service(fastapi_service_name)
            # Wait a moment for the service to stop and release database locks
            time.sleep(3)
    except Exception as e:
        click.echo(
            click.style(f"Warning: Could not check FastAPI service status: {e}", fg="yellow")
        )
        click.echo("Proceeding with dummy data generation...")

    try:
        # Generate dummy data with exclusive database access
        click.echo("Generating dummy data...")
        core_database = CoreDatabaseService(db_path)
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
        await generate_dummy_detections(
            data_manager,
            num_detections=count,
            max_days_ago=days,
            ioc_species_ratio=ioc_species_ratio,
        )
        click.echo(
            click.style(
                f"Dummy data generation complete. Generated {count} detections.", fg="green"
            )
        )
        if ioc_species_ratio > 0:
            ioc_count = int(count * ioc_species_ratio)
            common_count = int(count * (1 - ioc_species_ratio))
            click.echo(f"  - Approximately {ioc_count} detections are infrequent IOC species")
            click.echo(f"  - Approximately {common_count} detections are common species")

    finally:
        # Restart FastAPI if it was running before
        if fastapi_was_running:
            click.echo(f"Restarting FastAPI service ({fastapi_service_name})...")
            try:
                system_control.start_service(fastapi_service_name)
                click.echo(click.style("FastAPI service restarted successfully.", fg="green"))
            except Exception as e:
                click.echo(
                    click.style(f"Warning: Could not restart FastAPI service: {e}", fg="yellow")
                )
                click.echo("You may need to manually restart the service.")


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
@click.option(
    "--ioc-species-ratio",
    "-i",
    default=0.2,
    type=float,
    help="Ratio of detections that are random IOC species (0=disabled, 0.2=20%, default: 0.2)",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def main(count: int, days: int, ioc_species_ratio: float, verbose: bool) -> None:
    """Generate dummy detection data for testing BirdNET-Pi.

    This command creates realistic bird detection data for testing and development.
    By default, it generates 100 detections within the last 24 hours, with 20% being
    random IOC species as infrequent visitors.

    Examples:
        # Generate 100 detections from today only
        generate-dummy-data --days 0

        # Generate 500 detections from the last week
        generate-dummy-data --count 500 --days 7

        # Generate 50 detections with no IOC species
        generate-dummy-data --count 50 --ioc-species-ratio 0

        # Generate 200 detections with 40% IOC species
        generate-dummy-data --count 200 --ioc-species-ratio 0.4
    """
    if verbose:
        click.echo(f"Generating {count} detections from the last {days} day(s)...")
        if ioc_species_ratio > 0:
            pct = int(ioc_species_ratio * 100)
            click.echo(f"Including {pct}% random IOC species as infrequent visitors")

    asyncio.run(run(count, days, ioc_species_ratio))


if __name__ == "__main__":
    main()
