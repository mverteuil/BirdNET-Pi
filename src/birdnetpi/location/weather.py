"""Weather data management and fetching."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.detections.models import Detection
from birdnetpi.location.models import Weather


class WeatherManager:
    """Manage weather data fetching and caching."""

    def __init__(self, session: AsyncSession, latitude: float, longitude: float):
        self.session = session
        self.latitude = latitude
        self.longitude = longitude

    async def fetch_and_store_weather(self, timestamp: datetime) -> Weather:
        """Fetch weather data for a specific timestamp and store it.

        Args:
            timestamp: Datetime for which to fetch weather

        Returns:
            Weather object that was created
        """
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
            existing_hours = set(result.scalars().all())
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

                # Store the data
                for hour_data in weather_data:
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
            hourly_data.append(
                {
                    "timestamp": datetime.fromisoformat(timestamp_str),
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
