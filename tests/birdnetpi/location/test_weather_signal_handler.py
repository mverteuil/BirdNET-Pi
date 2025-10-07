"""Test the weather signal handler integration."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.location.weather import WeatherSignalHandler
from birdnetpi.notifications.signals import detection_signal


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
def config():
    """Create a test config with location."""
    return BirdNETConfig(
        latitude=63.4591,
        longitude=-19.3647,
    )


@pytest.fixture
def database_service(session):
    """Create a mock database service."""
    mock_service = MagicMock(spec=CoreDatabaseService)
    mock_service.get_async_db.return_value.__aenter__.return_value = session
    mock_service.get_async_db.return_value.__aexit__.return_value = None
    return mock_service


@pytest.fixture
def weather_handler(database_service, config):
    """Create a weather signal handler."""
    return WeatherSignalHandler(database_service, config.latitude, config.longitude)


def test_weather_handler_initialization(weather_handler, config):
    """Should weather handler initializes correctly."""
    assert weather_handler.latitude == config.latitude
    assert weather_handler.longitude == config.longitude
    assert weather_handler.database_service is not None


def test_weather_handler_register(weather_handler):
    """Should weather handler registers with the signal."""
    # Initially no receivers
    receivers_before = len(detection_signal.receivers)

    # Register the handler
    weather_handler.register()

    # Should have one more receiver
    receivers_after = len(detection_signal.receivers)
    assert receivers_after == receivers_before + 1

    # Clean up
    weather_handler.unregister()


def test_weather_handler_requires_location():
    """Should handler requires location coordinates."""
    mock_db = MagicMock(spec=CoreDatabaseService)

    # Should be able to create with valid coordinates
    handler = WeatherSignalHandler(mock_db, 63.4591, -19.3647)
    assert handler.latitude == 63.4591
    assert handler.longitude == -19.3647


@pytest.mark.asyncio
async def test_weather_handler_handles_detection_event(weather_handler, session, model_factory):
    """Should weather handler responds to detection events."""
    # Register the handler
    weather_handler.register()

    try:
        # Create a detection
        detection = model_factory.create_detection(
            species_tensor="Test_Bird",
            scientific_name="Testus birdus",
            confidence=0.95,
            timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
        )
        session.add(detection)
        await session.commit()

        # Mock the weather fetching
        with patch.object(weather_handler, "_fetch_and_link_weather", autospec=True) as mock_fetch:
            mock_fetch.return_value = asyncio.create_task(asyncio.sleep(0))

            # Simulate the detection signal being sent
            # This happens in an event loop context
            detection_signal.send(None, detection=detection)

            # Give async task time to be scheduled
            await asyncio.sleep(0.1)

            # Should have tried to fetch weather
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[0]
            assert call_args[0].id == detection.id

    finally:
        weather_handler.unregister()


@pytest.mark.asyncio
async def test_weather_handler_skips_detection_with_weather(
    weather_handler, session, model_factory
):
    """Should handler skips detections that already have weather."""
    weather_handler.register()

    try:
        # Create a weather record
        weather = model_factory.create_weather(
            timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
            latitude=63.4591,
            longitude=-19.3647,
            temperature=20.0,
        )
        session.add(weather)
        await session.commit()

        # Create a detection already linked to weather
        detection = model_factory.create_detection(
            species_tensor="Test_Bird",
            scientific_name="Testus birdus",
            confidence=0.95,
            timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
            weather_timestamp=weather.timestamp,
            weather_latitude=weather.latitude,
            weather_longitude=weather.longitude,
        )
        session.add(detection)
        await session.commit()

        with patch.object(weather_handler, "_fetch_and_link_weather", autospec=True) as mock_fetch:
            # Send the signal
            detection_signal.send(None, detection=detection)

            # Give it time
            await asyncio.sleep(0.1)

            # Should NOT have tried to fetch weather
            mock_fetch.assert_not_called()

    finally:
        weather_handler.unregister()


@pytest.mark.asyncio
async def test_fetch_and_link_weather_uses_existing(weather_handler, session, model_factory):
    """Should _fetch_and_link_weather uses existing weather when available."""
    # Create existing weather
    weather = model_factory.create_weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=15.0,
        humidity=60.0,
    )
    session.add(weather)

    # Create detection without weather
    detection = model_factory.create_detection(
        species_tensor="Test_Bird",
        scientific_name="Testus birdus",
        confidence=0.95,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    )
    session.add(detection)
    await session.commit()

    # Mock the WeatherManager's get_or_create_and_link_weather method
    with patch(
        "birdnetpi.location.weather.WeatherManager.get_or_create_and_link_weather", autospec=True
    ) as mock_fetch:
        mock_fetch.return_value = weather

        # Call the method
        await weather_handler._fetch_and_link_weather(detection)

        # Should have called the manager's method with the detection ID
        # With autospec=True, call_args[0] is self, call_args[1] is detection_id
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[0]
        assert call_args[1] == str(detection.id)


@pytest.mark.asyncio
async def test_fetch_and_link_weather_fetches_new(weather_handler, session, model_factory):
    """Should _fetch_and_link_weather fetches new weather when needed."""
    # Create detection without weather
    detection = model_factory.create_detection(
        species_tensor="Test_Bird",
        scientific_name="Testus birdus",
        confidence=0.95,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    )
    session.add(detection)
    await session.commit()

    # Mock the weather to be returned
    mock_weather = model_factory.create_weather(
        timestamp=datetime(2024, 1, 1, 12, tzinfo=UTC),
        latitude=63.4591,
        longitude=-19.3647,
        temperature=22.0,
        humidity=70.0,
    )

    # Mock the WeatherManager's get_or_create_and_link_weather method
    with patch(
        "birdnetpi.location.weather.WeatherManager.get_or_create_and_link_weather", autospec=True
    ) as mock_fetch:
        mock_fetch.return_value = mock_weather

        # Call the method
        await weather_handler._fetch_and_link_weather(detection)

        # Should have called the manager's method with the detection ID
        # With autospec=True, call_args[0] is self, call_args[1] is detection_id
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[0]
        assert call_args[1] == str(detection.id)


@pytest.mark.asyncio
async def test_weather_handler_handles_fetch_error(weather_handler, session, model_factory):
    """Should handler gracefully handles weather fetch errors."""
    # Create detection
    detection = model_factory.create_detection(
        species_tensor="Test_Bird",
        scientific_name="Testus birdus",
        confidence=0.95,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    )
    session.add(detection)
    await session.commit()

    # Mock the WeatherManager to raise error
    with patch(
        "birdnetpi.location.weather.WeatherManager.get_or_create_and_link_weather", autospec=True
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API Error")

        # Should not raise, just log error
        await weather_handler._fetch_and_link_weather(detection)

        # Should have tried to fetch
        # With autospec=True, call_args[0] is self, call_args[1] is detection_id
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[0]
        assert call_args[1] == str(detection.id)


def test_weather_handler_handles_no_event_loop(weather_handler, model_factory):
    """Should handler gracefully handles when no event loop is running."""
    # Create a detection
    detection = model_factory.create_detection(
        species_tensor="Test_Bird",
        scientific_name="Testus birdus",
        confidence=0.95,
        timestamp=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    )

    with patch("asyncio.get_running_loop", side_effect=RuntimeError("No event loop")):
        with patch.object(weather_handler, "_fetch_and_link_weather", autospec=True) as mock_fetch:
            # Should not raise, just skip
            weather_handler._handle_detection_event(None, detection=detection)

            # Should not have tried to fetch
            mock_fetch.assert_not_called()
