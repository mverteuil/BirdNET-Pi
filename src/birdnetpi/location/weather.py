"""Weather data management and fetching."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.detections.models import Detection
from birdnetpi.location.models import Weather
from birdnetpi.notifications.signals import detection_signal

if TYPE_CHECKING:
    from birdnetpi.config.models import BirdNETConfig
    from birdnetpi.database.core import DatabaseService

logger = logging.getLogger(__name__)


class WeatherManager:
    """Manage weather data fetching and caching."""

    def __init__(self, session: AsyncSession, latitude: float, longitude: float):
        self.session = session
        self.latitude = latitude
        self.longitude = longitude

    async def fetch_and_store_weather(self, timestamp: datetime) -> Weather:
        """Fetch weather data for a specific timestamp and store it.

        Args:
            timestamp: Datetime for which to fetch weather (should be in UTC)

        Returns:
            Weather object that was created
        """
        # Ensure timestamp is in UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        elif timestamp.tzinfo != UTC:
            timestamp = timestamp.astimezone(UTC)

        # Fetch weather data for single hour
        weather_data = await self.fetch_weather_range(timestamp, timestamp + timedelta(hours=1))

        if weather_data:
            # Add location to weather data
            weather_data[0]["latitude"] = self.latitude
            weather_data[0]["longitude"] = self.longitude
            weather = Weather(**weather_data[0])
            self.session.add(weather)
            await self.session.flush()
            return weather

        raise ValueError(f"No weather data available for {timestamp}")

    async def backfill_weather(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        skip_existing: bool = True,
    ) -> dict[str, int]:
        """Backfill weather for a specific time range.

        Args:
            start_date: Beginning of range (datetime)
            end_date: End of range (datetime)
            skip_existing: Skip hours that already have weather data

        Returns:
            Dict with statistics about the backfill operation
        """
        # Default to last 7 days if no range specified
        if not end_date:
            end_date = datetime.now(UTC)
        if not start_date:
            start_date = end_date - timedelta(days=7)

        stats = {"total_hours": 0, "fetched": 0, "skipped": 0, "errors": 0, "detections_updated": 0}

        # Round to hour boundaries
        current_hour = start_date.replace(minute=0, second=0, microsecond=0)
        end_hour = end_date.replace(minute=0, second=0, microsecond=0)

        # Process each hour in the range
        while current_hour <= end_hour:
            stats["total_hours"] += 1

            # Check if we already have weather for this hour
            if skip_existing:
                stmt = (
                    select(Weather)
                    .where(Weather.timestamp == current_hour)
                    .where(Weather.latitude == self.latitude)
                    .where(Weather.longitude == self.longitude)
                )
                result = await self.session.execute(stmt)
                existing = result.scalars().first()

                if existing:
                    stats["skipped"] += 1
                    current_hour += timedelta(hours=1)
                    continue

            # Fetch weather for this hour
            try:
                weather = await self.fetch_and_store_weather(current_hour)
                stats["fetched"] += 1

                # Update any detections in this hour
                updated = await self.link_detections_to_weather(
                    current_hour, current_hour + timedelta(hours=1), weather
                )
                stats["detections_updated"] += updated

            except Exception as e:
                print(f"Error fetching weather for {current_hour}: {e}")
                stats["errors"] += 1

            current_hour += timedelta(hours=1)

            # Rate limiting - be nice to free API
            if stats["fetched"] % 100 == 0:
                await asyncio.sleep(1)  # Pause every 100 requests

        await self.session.commit()
        return stats

    async def backfill_weather_bulk(
        self, start_date: datetime, end_date: datetime, skip_existing: bool = True
    ) -> dict[str, int]:
        """Bulk fetch weather data for better efficiency.

        Open-Meteo allows fetching multiple days at once.
        """
        # Calculate total days upfront
        # This gives us the actual number of days in the range
        time_diff = end_date - start_date
        total_days = max(
            1,
            int(time_diff.total_seconds() / 86400)
            + (1 if time_diff.total_seconds() % 86400 > 0 else 0),
        )

        stats = {
            "total_days": total_days,
            "api_calls": 0,
            "records_created": 0,
            "detections_updated": 0,
        }

        # Check what we already have
        if skip_existing:
            stmt = (
                select(Weather.timestamp)
                .where(Weather.timestamp >= start_date)
                .where(Weather.timestamp <= end_date)
                .where(Weather.latitude == self.latitude)
                .where(Weather.longitude == self.longitude)
            )
            result = await self.session.execute(stmt)
            # Normalize timestamps to remove timezone info for comparison
            # SQLite doesn't preserve timezone, so we normalize to naive datetimes
            existing_hours = {
                ts.replace(tzinfo=None) if ts.tzinfo else ts for ts in result.scalars().all()
            }
        else:
            existing_hours = set()

        # Fetch in chunks (Open-Meteo allows up to 16 days per request)
        chunk_size = timedelta(days=14)
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + chunk_size, end_date)

            # Skip if we have all data for this chunk
            hours_in_chunk = int((current_end - current_start).total_seconds() // 3600)
            hours_needed = []

            for i in range(hours_in_chunk):
                hour = current_start + timedelta(hours=i)
                hour = hour.replace(minute=0, second=0, microsecond=0)
                if hour not in existing_hours:
                    hours_needed.append(hour)

            if hours_needed:
                # Fetch weather for this chunk
                weather_data = await self.fetch_weather_range(current_start, current_end)
                stats["api_calls"] += 1

                # Store the data - only for hours we need
                for hour_data in weather_data:
                    # Round timestamp to hour for comparison
                    hour_timestamp = hour_data["timestamp"].replace(
                        minute=0, second=0, microsecond=0
                    )

                    # Normalize for comparison (remove timezone info)
                    hour_timestamp_normalized = (
                        hour_timestamp.replace(tzinfo=None)
                        if hour_timestamp.tzinfo
                        else hour_timestamp
                    )

                    # Skip if we already have this hour (check existing_hours set)
                    if skip_existing and hour_timestamp_normalized in existing_hours:
                        continue

                    # Add location to weather data
                    hour_data["latitude"] = self.latitude
                    hour_data["longitude"] = self.longitude
                    weather = Weather(**hour_data)
                    self.session.add(weather)
                    await self.session.flush()
                    stats["records_created"] += 1

                    # Link detections
                    updated = await self.link_detections_to_weather(
                        hour_data["timestamp"],
                        hour_data["timestamp"] + timedelta(hours=1),
                        weather,
                    )
                    stats["detections_updated"] += updated

            current_start = current_end

        await self.session.commit()
        return stats

    async def fetch_weather_range(
        self, start_date: datetime, end_date: datetime
    ) -> list[dict[str, Any]]:
        """Fetch weather data for a date range from Open-Meteo.

        Returns hourly weather data.
        """
        if start_date < datetime.now(UTC) - timedelta(days=5):
            # Use historical API
            url = "https://archive-api.open-meteo.com/v1/era5"
        else:
            # Use forecast API
            url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": start_date.date().isoformat(),
            "end_date": end_date.date().isoformat(),
            "hourly": "temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,"
            "wind_direction_10m,precipitation,rain,snowfall,cloud_cover,"
            "visibility,uv_index,direct_radiation",
            "timezone": "UTC",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        # Parse response into hourly records
        hourly_data = []
        for i, timestamp_str in enumerate(data["hourly"]["time"]):
            # Parse timestamp and ensure it's in UTC
            timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                # If no timezone info, assume UTC (as we requested UTC from API)
                timestamp = timestamp.replace(tzinfo=UTC)
            hourly_data.append(
                {
                    "timestamp": timestamp,
                    "temperature": data["hourly"]["temperature_2m"][i],
                    "humidity": data["hourly"]["relative_humidity_2m"][i],
                    "pressure": data["hourly"]["pressure_msl"][i],
                    "wind_speed": data["hourly"]["wind_speed_10m"][i],
                    "wind_direction": data["hourly"]["wind_direction_10m"][i],
                    "precipitation": data["hourly"]["precipitation"][i],
                    "rain": data["hourly"]["rain"][i],
                    "snow": data["hourly"]["snowfall"][i],
                    "cloud_cover": data["hourly"]["cloud_cover"][i],
                    "visibility": data["hourly"]["visibility"][i],
                    "uv_index": data["hourly"]["uv_index"][i],
                    "solar_radiation": data["hourly"]["direct_radiation"][i],
                    "source": "open-meteo",
                    "fetched_at": datetime.now(UTC),
                }
            )

        return hourly_data

    async def link_detections_to_weather(
        self, start_time: datetime, end_time: datetime, weather: Weather
    ) -> int:
        """Link detections in a time range to a weather record."""
        # Use SQLAlchemy 2.0 style update statement
        stmt = (
            update(Detection)
            .where(Detection.timestamp >= start_time)
            .where(Detection.timestamp < end_time)
            .where(Detection.weather_timestamp.is_(None))  # type: ignore[attr-defined]
            .values(
                weather_timestamp=weather.timestamp,
                weather_latitude=weather.latitude,
                weather_longitude=weather.longitude,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount  # type: ignore[attr-defined]

    async def get_or_create_and_link_weather(self, detection_id: str) -> Weather | None:
        """Get existing or create new weather and link it to a detection.

        This method handles the complete weather linking logic for a detection:
        1. Gets the detection from the database
        2. Checks if it already has weather linked (returns None if so)
        3. Rounds timestamp to the hour
        4. Looks for existing weather at that hour
        5. Creates new weather by fetching from API if needed
        6. Links the weather to the detection

        Args:
            detection_id: ID of the detection to process

        Returns:
            The Weather record that was linked, or None if failed or already linked
        """
        # Get the detection
        stmt = select(Detection).where(Detection.id == detection_id)
        result = await self.session.execute(stmt)
        detection = result.scalars().first()

        if not detection:
            logger.warning(f"Detection {detection_id} not found")
            return None

        # Check if already has weather
        if detection.weather_timestamp is not None:
            logger.debug(f"Detection {detection_id} already has weather data")
            return None

        # Round to the hour
        detection_hour = detection.timestamp.replace(minute=0, second=0, microsecond=0)

        # Check for existing weather
        stmt = (
            select(Weather)
            .where(Weather.timestamp == detection_hour)
            .where(Weather.latitude == self.latitude)
            .where(Weather.longitude == self.longitude)
        )
        result = await self.session.execute(stmt)
        weather = result.scalars().first()

        if weather:
            logger.debug(
                f"Using existing weather for {detection_hour}: "
                f"{weather.temperature}°C, {weather.humidity}% humidity"
            )
        else:
            # Fetch new weather
            try:
                weather = await self.fetch_and_store_weather(detection_hour)
                logger.info(
                    f"Fetched new weather for {detection_hour}: "
                    f"{weather.temperature}°C, {weather.humidity}% humidity"
                )
            except Exception as e:
                logger.error(f"Failed to fetch weather data: {e}")
                return None

        # Link weather to detection
        stmt = (
            update(Detection)
            .where(Detection.id == detection_id)
            .values(
                weather_timestamp=weather.timestamp,
                weather_latitude=weather.latitude,
                weather_longitude=weather.longitude,
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

        logger.info(
            f"Successfully linked weather to detection {detection_id}: "
            f"{weather.temperature}°C at {weather.timestamp}"
        )

        return weather

    async def smart_backfill(self) -> dict[str, Any]:
        """Intelligently backfill weather based on what's needed."""
        # Find date range of detections without weather
        stmt = select(func.min(Detection.timestamp), func.max(Detection.timestamp)).where(
            Detection.weather_timestamp.is_(None)  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        result = result.first()

        if not result[0]:
            return {"message": "No detections need weather data"}

        min_date, max_date = result

        # Get statistics
        total_stmt = select(func.count(Detection.id))
        result = await self.session.execute(total_stmt)
        total_detections = result.scalar()

        missing_stmt = select(func.count(Detection.id)).where(
            Detection.weather_timestamp.is_(None)  # type: ignore[attr-defined]
        )
        result = await self.session.execute(missing_stmt)
        missing_weather = result.scalar()

        print(f"Backfilling weather for {missing_weather}/{total_detections} detections")
        print(f"Date range: {min_date} to {max_date}")

        # Backfill in chunks
        return await self.backfill_weather_bulk(min_date, max_date)


class WeatherSignalHandler:
    """Handle weather data fetching for new detections."""

    def __init__(
        self,
        database_service: "DatabaseService",
        latitude: float,
        longitude: float,
    ):
        """Initialize the weather signal handler.

        Args:
            database_service: Database service for creating sessions
            latitude: Latitude for weather fetching (required)
            longitude: Longitude for weather fetching (required)
        """
        self.database_service = database_service
        self.latitude = latitude
        self.longitude = longitude
        self._background_tasks: set = set()

    def register(self) -> None:
        """Register the weather handler with the detection signal."""
        detection_signal.connect(self._handle_detection_event)
        logger.info("WeatherSignalHandler registered for detection events")

    def unregister(self) -> None:
        """Unregister the weather handler from the detection signal."""
        detection_signal.disconnect(self._handle_detection_event)
        logger.info("WeatherSignalHandler unregistered from detection events")

    def _handle_detection_event(
        self, sender: object, detection: Detection, **kwargs: object
    ) -> None:
        """Handle detection event by fetching and linking weather data.

        This method is called synchronously by the signal system, but spawns
        an async task to handle the weather fetching without blocking.

        Args:
            sender: The sender of the signal
            detection: The Detection object that was created
            **kwargs: Additional keyword arguments from the signal
        """
        if not detection or not isinstance(detection, Detection):
            return

        # Check if detection already has weather data
        if detection.weather_timestamp is not None:
            logger.debug(f"Detection {detection.id} already has weather data, skipping")
            return

        # Try to get the running event loop
        try:
            loop = asyncio.get_running_loop()
            # Create task to fetch and link weather
            task = loop.create_task(self._fetch_and_link_weather(detection))
            # Track task to prevent garbage collection
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            logger.debug(f"Scheduled weather fetch for detection {detection.id}")
        except RuntimeError:
            # No event loop running, log and skip
            logger.debug("No event loop running, skipping weather fetch for detection")

    async def _fetch_and_link_weather(self, detection: Detection) -> None:
        """Fetch and link weather data for a detection.

        Args:
            detection: The Detection to link weather to
        """
        try:
            async with self.database_service.get_async_db() as session:
                # Create weather manager for this session
                weather_manager = WeatherManager(session, self.latitude, self.longitude)

                # Use the manager's method to handle all the logic
                await weather_manager.get_or_create_and_link_weather(str(detection.id))

        except Exception as e:
            logger.error(f"Error fetching weather for detection {detection.id}: {e}")


def create_and_register_weather_handler(
    database_service: "DatabaseService",
    config: "BirdNETConfig",
) -> WeatherSignalHandler:
    """Create and register a weather signal handler.

    This is a convenience function to create and immediately register
    a weather signal handler.

    Args:
        database_service: Database service for persistence
        config: BirdNET configuration containing location data

    Returns:
        The registered WeatherSignalHandler instance
    """
    handler = WeatherSignalHandler(database_service, config.latitude, config.longitude)
    handler.register()
    return handler
