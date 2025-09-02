"""CLI command for backfilling weather data."""

import asyncio
from datetime import UTC, datetime, timedelta

import click

from birdnetpi.config import ConfigManager
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.location.weather import WeatherManager
from birdnetpi.system.path_resolver import PathResolver


@click.command()
@click.option(
    "--start",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
)
@click.option(
    "--end",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
)
@click.option(
    "--days",
    type=int,
    help="Number of days to backfill (alternative to --start/--end)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-fetch existing weather data",
)
@click.option(
    "--smart",
    is_flag=True,
    help="Automatically backfill based on detections without weather",
)
@click.option(
    "--bulk/--no-bulk",
    default=True,
    help="Use bulk API calls for efficiency (default: True)",
)
def backfill_weather(
    start: datetime | None,
    end: datetime | None,
    days: int | None,
    force: bool,
    smart: bool,
    bulk: bool,
) -> None:
    """Backfill weather data for detections.

    Examples:
        # Backfill last 7 days
        backfill-weather --days 7

        # Backfill specific date range
        backfill-weather --start 2024-01-01 --end 2024-01-31

        # Smart backfill based on detections
        backfill-weather --smart

        # Re-fetch existing data
        backfill-weather --days 3 --force
    """
    # Run the async function
    asyncio.run(_backfill_weather_async(start, end, days, force, smart, bulk))


async def _backfill_weather_async(
    start: datetime | None,
    end: datetime | None,
    days: int | None,
    force: bool,
    smart: bool,
    bulk: bool,
) -> None:
    """Async implementation of weather backfilling."""
    # Initialize components
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()

    # Get location from config
    latitude = config.latitude
    longitude = config.longitude

    if not latitude or not longitude:
        click.echo(
            click.style(
                "Error: Latitude and longitude must be configured in birdnetpi.yaml",
                fg="red",
            )
        )
        click.echo("Please set 'latitude' and 'longitude' in your configuration file.")
        return

    # Initialize database
    db_service = DatabaseService(path_resolver.get_database_path())
    await db_service.initialize()

    async with db_service.get_async_db() as session:
        weather_manager = WeatherManager(session, latitude, longitude)

        if smart:
            # Smart backfill based on detections without weather
            click.echo("Starting smart backfill based on detections without weather...")
            stats = await weather_manager.smart_backfill()

            if isinstance(stats, dict) and "message" in stats:
                click.echo(click.style(stats["message"], fg="green"))
            else:
                _display_stats(stats)
        else:
            # Determine date range
            if days:
                end_date = datetime.now(UTC)
                start_date = end_date - timedelta(days=days - 1)
                start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                click.echo(f"Backfilling {days} days from {start_date} to {end_date}")
            elif start and end:
                # Ensure timezone awareness
                start_date = start.replace(tzinfo=UTC) if start.tzinfo is None else start
                end_date = end.replace(tzinfo=UTC) if end.tzinfo is None else end
                click.echo(f"Backfilling from {start_date} to {end_date}")
            elif start:
                start_date = start.replace(tzinfo=UTC) if start.tzinfo is None else start
                end_date = datetime.now(UTC)
                click.echo(f"Backfilling from {start_date} to now")
            elif end:
                end_date = end.replace(tzinfo=UTC) if end.tzinfo is None else end
                start_date = end_date - timedelta(days=7)  # Default 7 days back
                click.echo(f"Backfilling 7 days before {end_date}")
            else:
                # Default: last 7 days
                end_date = datetime.now(UTC)
                start_date = end_date - timedelta(days=7)
                click.echo("No date range specified. Backfilling last 7 days...")

            # Perform backfill
            click.echo("Fetching weather data from Open-Meteo API...")
            click.echo(f"Location: {latitude:.4f}, {longitude:.4f}")
            click.echo(f"Skip existing: {not force}")

            if bulk:
                stats = await weather_manager.backfill_weather_bulk(
                    start_date=start_date,
                    end_date=end_date,
                    skip_existing=not force,
                )
            else:
                stats = await weather_manager.backfill_weather(
                    start_date=start_date,
                    end_date=end_date,
                    skip_existing=not force,
                )

            _display_stats(stats)

    # Clean up database connection
    await db_service.dispose()


def _display_stats(stats: dict) -> None:
    """Display backfill statistics in a formatted way."""
    click.echo("\n" + "=" * 50)
    click.echo(click.style("Backfill Complete!", fg="green", bold=True))
    click.echo("=" * 50)

    if "total_hours" in stats:
        # Hour-by-hour backfill stats
        click.echo(f"Total hours processed: {stats['total_hours']}")
        click.echo(f"Weather fetched: {stats['fetched']}")
        click.echo(f"Skipped (existing): {stats['skipped']}")
        click.echo(f"Errors: {stats['errors']}")
        click.echo(f"Detections updated: {stats['detections_updated']}")

        if stats["errors"] > 0:
            click.echo(
                click.style(
                    f"⚠️  {stats['errors']} errors occurred during backfill",
                    fg="yellow",
                )
            )
    elif "total_days" in stats:
        # Bulk backfill stats
        click.echo(f"Total days processed: {stats['total_days']}")
        click.echo(f"API calls made: {stats['api_calls']}")
        click.echo(f"Weather records created: {stats['records_created']}")
        click.echo(f"Detections updated: {stats['detections_updated']}")

    if stats.get("detections_updated", 0) > 0:
        detections_updated = stats["detections_updated"]
        click.echo(
            click.style(
                f"\n✅ Successfully linked {detections_updated} detections to weather data!",
                fg="green",
                bold=True,
            )
        )
    else:
        click.echo(
            click.style(
                "\nNo detections were updated. All detections may already have weather data.",
                fg="yellow",
            )
        )


if __name__ == "__main__":
    backfill_weather()
