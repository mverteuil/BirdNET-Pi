"""Test the WeatherManager class."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from birdnetpi.detections.models import Detection
from birdnetpi.location.models import Weather
from birdnetpi.location.weather import WeatherManager


@pytest.fixture
async def engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest.fixture
async def session(engine):
    """Create an async database session."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:  # type: ignore[attr-defined]
        yield session


@pytest.fixture
def weather_manager(session):
    """Create a WeatherManager instance."""
    return WeatherManager(session, latitude=63.4591, longitude=-19.3647)


@pytest.fixture
def mock_weather_response():
    """Mock Open-Meteo API response."""
    return {
        "hourly": {
            "time": [
                "2024-01-01T00:00",
                "2024-01-01T01:00",
                "2024-01-01T02:00",
            ],
            "temperature_2m": [20.0, 21.0, 22.0],
            "relative_humidity_2m": [65.0, 66.0, 67.0],
            "pressure_msl": [1013.0, 1014.0, 1015.0],
            "wind_speed_10m": [10.0, 11.0, 12.0],
            "wind_direction_10m": [180, 185, 190],
            "precipitation": [0.0, 0.1, 0.2],
            "rain": [0.0, 0.1, 0.2],
            "snowfall": [0.0, 0.0, 0.0],
            "cloud_cover": [25, 30, 35],
            "visibility": [10000, 9500, 9000],
            "uv_index": [0.0, 0.0, 0.0],
            "direct_radiation": [0.0, 0.0, 0.0],
        }
    }


def test_weather_manager_initialization(weather_manager):
    """Should weatherManager initialization."""
    assert weather_manager.latitude == 63.4591
    assert weather_manager.longitude == -19.3647
    assert weather_manager.session is not None


@pytest.mark.asyncio
async def test_fetch_weather_range(weather_manager, mock_weather_response):
    """Should fetching weather data from API."""
    with patch("birdnetpi.location.weather.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_weather_response
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        start_date = datetime(2024, 1, 1, tzinfo=UTC)
        end_date = datetime(2024, 1, 2, tzinfo=UTC)

        weather_data = await weather_manager.fetch_weather_range(start_date, end_date)

        assert len(weather_data) == 3
        assert weather_data[0]["temperature"] == 20.0
        assert weather_data[1]["humidity"] == 66.0
        assert weather_data[2]["wind_speed"] == 12.0
        assert all(w["source"] == "open-meteo" for w in weather_data)


@pytest.mark.asyncio
async def test_fetch_weather_range_historical_api(weather_manager, mock_weather_response):
    """Should historical API is used for old dates."""
    with patch("birdnetpi.location.weather.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_weather_response
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Use a date more than 5 days ago
        old_date = datetime.now(UTC) - timedelta(days=10)
        start_date = old_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)

        await weather_manager.fetch_weather_range(start_date, end_date)

        # Verify historical API URL was used
        call_args = mock_client.get.call_args
        assert "archive-api.open-meteo.com" in call_args[0][0]


@pytest.mark.asyncio
async def test_fetch_weather_range_forecast_api(weather_manager, mock_weather_response):
    """Should forecast API is used for recent dates."""
    with patch("birdnetpi.location.weather.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_weather_response
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Use a recent date
        recent_date = datetime.now(UTC) - timedelta(days=2)
        start_date = recent_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)

        await weather_manager.fetch_weather_range(start_date, end_date)

        # Verify forecast API URL was used
        call_args = mock_client.get.call_args
        assert "api.open-meteo.com" in call_args[0][0]
        assert "archive-api" not in call_args[0][0]


@pytest.mark.asyncio
async def test_fetch_and_store_weather(weather_manager, session, mock_weather_response):
    """Should fetching and storing weather for a specific timestamp."""
    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        mock_fetch.return_value = [
            {
                "timestamp": datetime(2024, 1, 1, 0, tzinfo=UTC),
                "temperature": 20.0,
                "humidity": 65.0,
                "source": "open-meteo",
                "fetched_at": datetime.now(UTC),
            }
        ]

        timestamp = datetime(2024, 1, 1, 0, tzinfo=UTC)
        weather = await weather_manager.fetch_and_store_weather(timestamp)

        assert weather.temperature == 20.0
        assert weather.humidity == 65.0
        assert weather.source == "open-meteo"

        # Verify it was saved to database
        saved = await session.get(Weather, (weather.timestamp, weather.latitude, weather.longitude))
        assert saved is not None
        assert saved.temperature == 20.0


@pytest.mark.asyncio
async def test_fetch_and_store_weather_no_data(weather_manager):
    """Should error handling when no weather data is available."""
    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        mock_fetch.return_value = []

        timestamp = datetime(2024, 1, 1, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="No weather data available"):
            await weather_manager.fetch_and_store_weather(timestamp)


@pytest.mark.asyncio
async def test_link_detections_to_weather(weather_manager, session):
    """Should linking detections to weather records."""
    # Create weather record
    weather = Weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=20.0,
        humidity=65.0,
    )
    session.add(weather)
    await session.commit()

    # Create detections in the same hour
    base_time = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)
    for i in range(3):
        detection = Detection(
            species_tensor=f"Bird_{i}",
            scientific_name=f"Species {i}",
            confidence=0.9,
            timestamp=base_time + timedelta(minutes=i),
        )
        session.add(detection)

    # Create detection in different hour (shouldn't be linked)
    other_detection = Detection(
        species_tensor="Other_Bird",
        scientific_name="Other Species",
        confidence=0.8,
        timestamp=datetime(2024, 1, 1, 13, 30, tzinfo=UTC),
    )
    session.add(other_detection)
    await session.commit()

    # Link detections
    start_time = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 13, 0, tzinfo=UTC)
    updated = await weather_manager.link_detections_to_weather(start_time, end_time, weather)

    assert updated == 3

    # Verify correct detections were linked
    stmt = select(Detection).where(Detection.weather_timestamp.isnot(None))  # type: ignore[attr-defined]
    result = await session.execute(stmt)
    linked = result.scalars().all()
    assert len(linked) == 3
    # SQLite doesn't preserve timezone, so we compare after ensuring timezone
    for d in linked:
        detection_ts = d.weather_timestamp
        if detection_ts.tzinfo is None:
            detection_ts = detection_ts.replace(tzinfo=UTC)
        assert detection_ts == weather.timestamp
    assert all(d.weather_latitude == weather.latitude for d in linked)
    assert all(d.weather_longitude == weather.longitude for d in linked)

    # Verify other detection wasn't linked
    await session.refresh(other_detection)
    assert other_detection.weather_timestamp is None


@pytest.mark.asyncio
async def test_link_detections_skips_already_linked(weather_manager, session):
    """Should link_detections_to_weather skips already linked detections."""
    # Create two weather records
    weather1 = Weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=20.0,
    )
    weather2 = Weather(
        timestamp=datetime(2024, 1, 1, 13, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=22.0,
    )
    session.add_all([weather1, weather2])
    await session.commit()

    # Create detection already linked to weather1
    detection = Detection(
        species_tensor="Bird",
        scientific_name="Species",
        confidence=0.9,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
        weather_timestamp=weather1.timestamp,
    )
    session.add(detection)
    await session.commit()

    # Try to link to weather2
    start_time = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 13, 0, tzinfo=UTC)
    updated = await weather_manager.link_detections_to_weather(start_time, end_time, weather2)

    assert updated == 0  # No updates because detection already has weather

    # Verify detection still linked to weather1
    await session.refresh(detection)
    # Handle timezone comparison for SQLite
    detection_ts = detection.weather_timestamp
    if detection_ts and detection_ts.tzinfo is None:
        detection_ts = detection_ts.replace(tzinfo=UTC)
    assert detection_ts == weather1.timestamp


@pytest.mark.asyncio
async def test_backfill_weather(weather_manager, session):
    """Should backfilling weather for a time range."""
    with patch.object(weather_manager, "fetch_and_store_weather") as mock_fetch:
        # Mock weather creation
        async def create_weather(timestamp):
            weather = Weather(
                timestamp=timestamp,
                latitude=63.4591,
                longitude=-19.3647,
                temperature=20.0,
                humidity=65.0,
            )
            session.add(weather)
            await session.flush()
            return weather

        mock_fetch.side_effect = create_weather

        # Create detections needing weather
        base_time = datetime(2024, 1, 1, 12, tzinfo=UTC)
        for i in range(3):
            detection = Detection(
                species_tensor=f"Bird_{i}",
                scientific_name=f"Species {i}",
                confidence=0.9,
                timestamp=base_time + timedelta(hours=i),
            )
            session.add(detection)
        await session.commit()

        # Backfill weather
        start_date = datetime(2024, 1, 1, 12, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 15, tzinfo=UTC)
        stats = await weather_manager.backfill_weather(start_date, end_date)

        assert stats["total_hours"] == 4  # 12:00, 13:00, 14:00, 15:00
        assert stats["fetched"] == 4
        assert stats["skipped"] == 0
        assert stats["errors"] == 0
        assert stats["detections_updated"] == 3


@pytest.mark.asyncio
async def test_backfill_weather_skip_existing(weather_manager, session):
    """Should backfill skips existing weather records when requested."""
    # Create existing weather
    existing_weather = Weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=15.0,
        humidity=60.0,
    )
    session.add(existing_weather)
    await session.commit()

    with patch.object(weather_manager, "fetch_and_store_weather") as mock_fetch:
        mock_fetch.return_value = MagicMock(id=999)

        start_date = datetime(2024, 1, 1, 12, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 14, tzinfo=UTC)
        stats = await weather_manager.backfill_weather(start_date, end_date, skip_existing=True)

        assert stats["total_hours"] == 3  # 12:00, 13:00, 14:00
        assert stats["skipped"] == 1  # 12:00 was skipped
        assert stats["fetched"] == 2  # 13:00 and 14:00 were fetched


@pytest.mark.asyncio
async def test_backfill_weather_error_handling(weather_manager):
    """Should error handling in backfill_weather."""
    with patch.object(weather_manager, "fetch_and_store_weather") as mock_fetch:
        mock_fetch.side_effect = Exception("API Error")

        start_date = datetime(2024, 1, 1, 12, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 13, tzinfo=UTC)

        # Should not raise, but count errors
        stats = await weather_manager.backfill_weather(start_date, end_date)

        assert stats["total_hours"] == 2
        assert stats["errors"] == 2
        assert stats["fetched"] == 0


@pytest.mark.asyncio
async def test_backfill_weather_bulk(weather_manager, session):
    """Should bulk weather backfilling."""
    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        mock_fetch.return_value = [
            {
                "timestamp": datetime(2024, 1, 1, i, tzinfo=UTC),
                "temperature": 20.0 + i,
                "humidity": 65.0,
                "source": "open-meteo",
                "fetched_at": datetime.now(UTC),
            }
            for i in range(24)
        ]

        start_date = datetime(2024, 1, 1, tzinfo=UTC)
        end_date = datetime(2024, 1, 2, tzinfo=UTC)

        stats = await weather_manager.backfill_weather_bulk(
            start_date, end_date, skip_existing=False
        )

        assert stats["total_days"] == 1  # Jan 1 to Jan 2 is 1 day
        assert stats["api_calls"] == 1  # One bulk API call
        assert stats["records_created"] == 24  # 24 hours of data

        # Verify records were created
        stmt = select(func.count(Weather.timestamp))
        result = await session.execute(stmt)
        count = result.scalar()
        assert count == 24


@pytest.mark.asyncio
async def test_backfill_weather_bulk_skip_existing(weather_manager, session):
    """Should bulk backfill skips existing records."""
    # Create some existing weather records
    for hour in [0, 6, 12, 18]:
        weather = Weather(
            timestamp=datetime(2024, 1, 1, hour, tzinfo=UTC),
            latitude=63.4591,
            longitude=-19.3647,
            temperature=15.0,
            humidity=60.0,
        )
        session.add(weather)
    await session.commit()

    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        # Return data for all hours
        mock_fetch.return_value = [
            {
                "timestamp": datetime(2024, 1, 1, i, tzinfo=UTC),
                "temperature": 20.0 + i,
                "humidity": 65.0,
                "source": "open-meteo",
                "fetched_at": datetime.now(UTC),
            }
            for i in range(24)
        ]

        start_date = datetime(2024, 1, 1, tzinfo=UTC)
        end_date = datetime(2024, 1, 2, tzinfo=UTC)

        stats = await weather_manager.backfill_weather_bulk(
            start_date, end_date, skip_existing=True
        )

        assert stats["total_days"] == 1  # Jan 1 to Jan 2 is 1 day
        # Should only create records for missing hours (24 - 4 existing = 20)
        assert stats["records_created"] == 20

        # Verify total records (4 existing + 20 new)
        stmt = select(func.count(Weather.timestamp))
        result = await session.execute(stmt)
        count = result.scalar()
        assert count == 24


@pytest.mark.asyncio
async def test_smart_backfill(weather_manager, session):
    """Should smart backfill based on detections without weather."""
    # Create detections across different times
    timestamps = [
        datetime(2024, 1, 1, 10, tzinfo=UTC),
        datetime(2024, 1, 1, 14, tzinfo=UTC),
        datetime(2024, 1, 2, 8, tzinfo=UTC),
    ]

    for ts in timestamps:
        detection = Detection(
            species_tensor="Bird",
            scientific_name="Species",
            confidence=0.9,
            timestamp=ts,
        )
        session.add(detection)
    await session.commit()

    with patch.object(weather_manager, "backfill_weather_bulk") as mock_backfill:
        mock_backfill.return_value = {
            "total_days": 2,
            "api_calls": 1,
            "records_created": 48,
            "detections_updated": 3,
        }

        result = await weather_manager.smart_backfill()

        # Should call backfill with correct date range
        mock_backfill.assert_called_once()
        call_args = mock_backfill.call_args[0]
        # Database may return naive datetimes, so compare without timezone
        assert call_args[0].replace(tzinfo=None) == timestamps[0].replace(tzinfo=None)  # min date
        assert call_args[1].replace(tzinfo=None) == timestamps[2].replace(tzinfo=None)  # max date

        assert result["detections_updated"] == 3


@pytest.mark.asyncio
async def test_smart_backfill_no_detections(weather_manager, session):
    """Should smart backfill when no detections need weather."""
    # Create detection with weather already linked
    weather = Weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=20.0,
    )
    session.add(weather)
    await session.commit()

    detection = Detection(
        species_tensor="Bird",
        scientific_name="Species",
        confidence=0.9,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
        weather_timestamp=weather.timestamp,
    )
    session.add(detection)
    await session.commit()

    result = await weather_manager.smart_backfill()

    assert result["message"] == "No detections need weather data"


@pytest.mark.asyncio
async def test_backfill_weather_bulk_multi_day(weather_manager, session):
    """Should bulk backfill correctly calculates total_days for various date ranges."""
    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        # Test 3 days
        mock_fetch.return_value = [
            {
                "timestamp": datetime(2024, 1, d, h, tzinfo=UTC),
                "temperature": 20.0,
                "humidity": 65.0,
                "source": "open-meteo",
                "fetched_at": datetime.now(UTC),
            }
            for d in range(1, 4)  # Days 1-3
            for h in range(24)  # All hours
        ]

        start_date = datetime(2024, 1, 1, tzinfo=UTC)
        end_date = datetime(2024, 1, 3, 23, 59, 59, tzinfo=UTC)  # End of day 3

        stats = await weather_manager.backfill_weather_bulk(
            start_date, end_date, skip_existing=False
        )

        assert stats["total_days"] == 3  # Should be 3 days, not 14 or 42
        assert stats["api_calls"] == 1
        assert stats["records_created"] == 72  # 3 days * 24 hours

    # Clean up previous weather records to avoid conflicts
    from sqlalchemy import delete

    await session.execute(delete(Weather))
    await session.commit()

    # Test partial day (less than 24 hours)
    with patch.object(weather_manager, "fetch_weather_range") as mock_fetch:
        mock_fetch.return_value = [
            {
                "timestamp": datetime(2024, 1, 1, h, tzinfo=UTC),
                "temperature": 20.0,
                "humidity": 65.0,
                "source": "open-meteo",
                "fetched_at": datetime.now(UTC),
            }
            for h in range(12)  # Only 12 hours
        ]

        start_date = datetime(2024, 1, 1, 0, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 11, tzinfo=UTC)  # Same day, 12 hours

        stats = await weather_manager.backfill_weather_bulk(
            start_date, end_date, skip_existing=False
        )

        assert stats["total_days"] == 1  # Still 1 day even if partial
        assert stats["records_created"] == 12  # 12 hours


@pytest.mark.asyncio
async def test_rate_limiting_in_backfill(weather_manager):
    """Should rate limiting is applied during backfill."""
    with patch.object(weather_manager, "fetch_and_store_weather") as mock_fetch:
        mock_fetch.return_value = MagicMock(id=1)

        with patch("asyncio.sleep") as mock_sleep:
            # Backfill exactly 100 hours to trigger rate limit
            start_date = datetime(2024, 1, 1, tzinfo=UTC)
            end_date = start_date + timedelta(hours=100)

            await weather_manager.backfill_weather(start_date, end_date)

            # Should have called sleep once after 100 fetches
            mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_weather_manager_session_handling(session):
    """Should weatherManager properly uses the session."""
    manager = WeatherManager(session, 40.0, -74.0)

    # Create a weather record
    weather = Weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=20.0,
    )
    session.add(weather)
    await session.commit()

    # Create detection
    detection = Detection(
        species_tensor="Bird",
        scientific_name="Species",
        confidence=0.9,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    )
    session.add(detection)
    await session.commit()

    # Link should work with the session
    updated = await manager.link_detections_to_weather(
        datetime(2024, 1, 1, 12, tzinfo=UTC), datetime(2024, 1, 1, 13, tzinfo=UTC), weather
    )

    assert updated == 1

    # Verify the update persisted
    await session.refresh(detection)
    # Handle timezone comparison for SQLite (doesn't preserve timezone)
    detection_ts = detection.weather_timestamp
    if detection_ts and detection_ts.tzinfo is None:
        detection_ts = detection_ts.replace(tzinfo=UTC)
    assert detection_ts == weather.timestamp


# Tests for refactored methods
class TestWeatherManagerRefactoredMethods:
    """Test the new refactored methods in WeatherManager."""

    @pytest.mark.asyncio
    async def test_get_existing_weather_hours(self, weather_manager, session):
        """Should _get_existing_weather_hours method."""
        # Create some weather records
        weather1 = Weather(
            timestamp=datetime(2024, 1, 1, 10, tzinfo=UTC),
            latitude=63.4591,
            longitude=-19.3647,
            temperature=20.0,
            humidity=65,
        )
        weather2 = Weather(
            timestamp=datetime(2024, 1, 1, 11, tzinfo=UTC),
            latitude=63.4591,
            longitude=-19.3647,
            temperature=21.0,
            humidity=66,
        )
        session.add(weather1)
        session.add(weather2)
        await session.commit()

        # Test the method
        start = datetime(2024, 1, 1, 9, tzinfo=UTC)
        end = datetime(2024, 1, 1, 12, tzinfo=UTC)
        existing = await weather_manager._get_existing_weather_hours(start, end)

        assert len(existing) == 2
        # Convert to naive datetime for comparison (SQLite doesn't preserve timezone)
        existing_naive = {dt.replace(tzinfo=None) if dt.tzinfo else dt for dt in existing}
        assert datetime(2024, 1, 1, 10) in existing_naive
        assert datetime(2024, 1, 1, 11) in existing_naive
        assert datetime(2024, 1, 1, 9) not in existing_naive
        assert datetime(2024, 1, 1, 12) not in existing_naive

    @pytest.mark.asyncio
    async def test_determine_chunk_size(self, weather_manager):
        """Should _determine_chunk_size method."""
        now = datetime.now(UTC)

        # Test forecast API (within 5 days)
        recent_date = now - timedelta(days=2)
        chunk_size = weather_manager._determine_chunk_size(recent_date)
        assert chunk_size == timedelta(days=14)  # Forecast API uses 14-day chunks

        # Test historical API (older than 5 days)
        old_date = now - timedelta(days=10)
        chunk_size = weather_manager._determine_chunk_size(old_date)
        assert chunk_size == timedelta(days=7)  # Historical API uses 7-day chunks

    @pytest.mark.asyncio
    async def test_process_weather_hour(self, weather_manager, session):
        """Should _process_weather_hour method."""
        # Test processing a new weather hour
        hour_data = {
            "timestamp": datetime(2024, 1, 1, 10, tzinfo=UTC),
            "temperature": 20.0,
            "humidity": 65,
            "pressure": 1013.0,
            "precipitation": 0.0,
            "wind_speed": 5.0,
            "wind_direction": 180,
            "cloud_cover": 50,
        }
        stats = {"records_created": 0, "detections_updated": 0, "errors": 0}

        success = await weather_manager._process_weather_hour(hour_data, stats)
        assert success
        assert stats["records_created"] == 1
        assert stats["errors"] == 0

        # Try processing the same hour again (duplicate handling)
        stats2 = {"records_created": 0, "detections_updated": 0, "errors": 0}

        # The method handles duplicates gracefully and returns False
        success2 = await weather_manager._process_weather_hour(hour_data, stats2)
        assert not success2  # Should return False for duplicate
        assert stats2["records_created"] == 0  # No new record created

        # Verify the weather record was created
        result = await session.execute(
            select(Weather).where(Weather.timestamp == hour_data["timestamp"])
        )
        weather = result.scalar_one()
        assert weather.temperature == 20.0
        assert weather.humidity == 65
        assert weather.pressure == 1013.0
