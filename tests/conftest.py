import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import matplotlib
import pytest
from dependency_injector import providers
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import AudioFile, Detection, DetectionWithTaxa
from birdnetpi.location.models import Weather
from birdnetpi.releases.asset_manifest import AssetManifest
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")

# Pyleak is available for manual use in tests via @pytest.mark.no_leaks
# The pytest plugin automatically handles this when tests are marked with @pytest.mark.no_leaks


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Get the absolute path to the repository root.

    This fixture provides a consistent way to access the repository root
    regardless of where tests are located or how they're organized.
    """
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def path_resolver(tmp_path: Path, repo_root: Path) -> PathResolver:
    """Provide a PathResolver with proper separation of read-only and writable paths.

    IMPORTANT: This fixture properly isolates test data by:
    1. Using REAL repo paths for READ-ONLY assets that tests need to access:
       - Models (*.tflite files)
       - IOC reference database
       - Avibase multilingual database
       - PatLevin labels database
       - Static files (CSS, JS, images)
       - Templates (HTML templates)
       - Config template (birdnetpi.yaml.template)

    2. Using TEMP paths for WRITABLE data to prevent test pollution:
       - Main database (birdnetpi.db) - prevents tests from writing to data/database/
       - Config file (birdnetpi.yaml) - prevents tests from writing to data/config/
       - Log files - prevents tests from writing to data/logs/
       - Export files - prevents tests from writing to data/exports/

    This separation is critical because:
    - Tests need real assets (models, IOC db) to function properly
    - Tests must NOT write to the real data/ directory (would pollute the repo)
    - PathResolver has individual methods for each path type specifically
      to enable this kind of mocking/overriding

    DO NOT use environment variables to control paths - that approach fails because
    it affects ALL paths uniformly, when we need selective path overriding.
    """
    real_data_dir = repo_root / "data"
    real_app_dir = repo_root

    # Create resolver with real paths
    resolver = PathResolver()

    # Create temp directories for writable data
    temp_database_dir = tmp_path / "database"
    temp_database_dir.mkdir(parents=True)
    temp_config_dir = tmp_path / "config"
    temp_config_dir.mkdir(parents=True)
    # Override WRITABLE paths to use temp directory
    resolver.get_database_path = lambda: temp_database_dir / "birdnetpi.db"
    resolver.get_birdnetpi_config_path = lambda: temp_config_dir / "birdnetpi.yaml"

    # Keep READ-ONLY paths pointing to real repo locations
    # These are already correct from the base PathResolver, but let's be explicit:
    resolver.get_ioc_database_path = lambda: real_data_dir / "database" / "ioc_reference.db"
    resolver.get_avibase_database_path = lambda: real_data_dir / "database" / "avibase_database.db"
    resolver.get_patlevin_database_path = (
        lambda: real_data_dir / "database" / "patlevin_database.db"
    )
    resolver.get_models_dir = lambda: real_data_dir / "models"
    resolver.get_model_path = lambda model_filename: (
        real_data_dir
        / "models"
        / (model_filename if model_filename.endswith(".tflite") else f"{model_filename}.tflite")
    )
    resolver.get_config_template_path = lambda: real_app_dir / "config_templates" / "birdnetpi.yaml"
    resolver.get_static_dir = lambda: real_app_dir / "src" / "birdnetpi" / "web" / "static"
    resolver.get_templates_dir = lambda: real_app_dir / "src" / "birdnetpi" / "web" / "templates"
    resolver.get_repo_path = lambda: real_app_dir  # Repository root for tests

    # For config tests, copy template to temp config location
    template_path = Path(resolver.get_config_template_path())
    if template_path.exists():
        config_path = Path(resolver.get_birdnetpi_config_path())
        config_path.write_text(template_path.read_text())

    return resolver


@pytest.fixture
async def app_with_temp_data(path_resolver):
    """Create FastAPI app with properly isolated paths.

    This fixture uses the path_resolver fixture from tests/conftest.py
    which properly separates read-only assets (models, IOC db) from writable
    data (database, config, logs) to prevent test pollution.

    IMPORTANT: We must override the Container providers BEFORE creating the app
    because sqladmin_view_routes.setup_sqladmin() calls container.core_database()
    during app creation, which would instantiate DatabaseService with the default
    /var/lib/birdnetpi path and cause a PermissionError.
    """
    # Override the Container's providers at the class level BEFORE app creation
    # This ensures that when sqladmin calls container.core_database(),
    # it gets our test version with the temp path
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))

    # Create a test config using our ConfigManager with test path_resolver
    manager = ConfigManager(path_resolver)
    test_config = manager.load()
    Container.config.override(providers.Singleton(lambda: test_config))

    # Create a test database service with the temp path
    temp_db_service = CoreDatabaseService(path_resolver.get_database_path())

    # Initialize the database (create tables) - await it properly
    await temp_db_service.initialize()

    Container.core_database.override(providers.Singleton(lambda: temp_db_service))

    # Mock the cache service to avoid Redis connection issues in tests
    mock_cache = MagicMock(spec=Cache)
    mock_cache.get.return_value = None
    mock_cache.set.return_value = True
    mock_cache.delete.return_value = True
    mock_cache.clear.return_value = True
    mock_cache.ping.return_value = True
    mock_cache.get_stats.return_value = {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "deletes": 0,
        "pattern_deletes": 0,
        "errors": 0,
        "hit_rate": 0.0,
        "total_requests": 0,
        "backend": "mock",
    }
    Container.cache_service.override(providers.Singleton(lambda: mock_cache))

    # Now create the app with our overridden providers
    app = create_app()

    # Store a reference to the temp_db_service to prevent garbage collection
    app._test_db_service = temp_db_service  # type: ignore[attr-defined]

    yield app

    # Clean up after the test
    # Dispose the async engine properly
    if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
        await temp_db_service.async_engine.dispose()

    # Reset container overrides
    Container.path_resolver.reset_override()
    Container.database_path.reset_override()
    Container.config.reset_override()
    Container.core_database.reset_override()
    Container.cache_service.reset_override()


@pytest.fixture
async def async_in_memory_session():
    """Create real in-memory async SQLite session with full schema for integration tests.

    This fixture provides a complete test database environment:
    - Creates all SQLModel tables (Detection, AudioFile, Weather, etc.)
    - Provides async session for database operations
    - Properly cleans up to prevent file descriptor leaks

    Use this when you need to test actual database interactions without mocking.

    Example:
        async def test_detection_persistence(async_in_memory_session):
            detection = Detection(
                scientific_name="Turdus migratorius",
                confidence=0.95,
                species_tensor="Turdus migratorius_American Robin",
            )
            async_in_memory_session.add(detection)
            await async_in_memory_session.commit()

            # Verify it persisted
            from sqlalchemy import select
            result = await async_in_memory_session.execute(
                select(Detection).where(Detection.scientific_name == "Turdus migratorius")
            )
            found = result.scalar_one()
            assert found.confidence == 0.95
    """
    # Create async engine for in-memory SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,  # Set to True for SQL debugging
    )

    # Create all tables from SQLModel metadata
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Create session factory
    session_local = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create session explicitly to help pyright understand the type
    session = cast(AsyncSession, session_local())
    try:
        yield session
    finally:
        await session.close()
        # IMPORTANT: Dispose the engine to prevent file descriptor leaks
        await engine.dispose()


@pytest.fixture
async def populated_test_db(async_in_memory_session: AsyncSession, model_factory):
    """Database pre-populated with test data for integration tests.

    This fixture extends async_in_memory_session by adding common test data:
    - 3 detections (robin, crow, cardinal)
    - 2 audio files
    - 1 weather record

    Use this when you need a realistic database state without manual setup.

    Example:
        async def test_detection_query(populated_test_db):
            # Database already has 3 detections
            from sqlalchemy import select
            result = await populated_test_db.execute(select(Detection))
            detections = result.scalars().all()
            assert len(detections) == 3

            # Known data available for assertions
            robin = await populated_test_db.execute(
                select(Detection).where(Detection.common_name == "American Robin")
            )
            assert robin.scalar_one().confidence == 0.95
    """
    # Create audio files first (referenced by detections)
    audio_file_1 = model_factory.create_audio_file(
        file_path=Path("/tmp/test_audio_1.wav"),
        duration=3.0,
    )
    audio_file_2 = model_factory.create_audio_file(
        file_path=Path("/tmp/test_audio_2.wav"),
        duration=3.0,
    )
    async_in_memory_session.add(audio_file_1)
    async_in_memory_session.add(audio_file_2)
    await async_in_memory_session.commit()
    await async_in_memory_session.refresh(audio_file_1)
    await async_in_memory_session.refresh(audio_file_2)

    # Create weather record (optional for detections)
    weather = model_factory.create_weather(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        latitude=40.7128,
        longitude=-74.0060,
        temperature=15.0,
        humidity=60.0,
    )
    async_in_memory_session.add(weather)
    await async_in_memory_session.commit()

    # Create detections with known data
    detection_robin = model_factory.create_detection(
        scientific_name="Turdus migratorius",
        common_name="American Robin",
        species_tensor="Turdus migratorius_American Robin",
        confidence=0.95,
        timestamp=datetime(2025, 1, 1, 8, 30, 0, tzinfo=UTC),
        audio_file_id=audio_file_1.id,
        latitude=40.7128,
        longitude=-74.0060,
    )

    detection_crow = model_factory.create_detection(
        scientific_name="Corvus brachyrhynchos",
        common_name="American Crow",
        species_tensor="Corvus brachyrhynchos_American Crow",
        confidence=0.88,
        timestamp=datetime(2025, 1, 1, 9, 15, 0, tzinfo=UTC),
        audio_file_id=audio_file_2.id,
        latitude=40.7128,
        longitude=-74.0060,
    )

    detection_cardinal = model_factory.create_detection(
        scientific_name="Cardinalis cardinalis",
        common_name="Northern Cardinal",
        species_tensor="Cardinalis cardinalis_Northern Cardinal",
        confidence=0.92,
        timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
        latitude=40.7128,
        longitude=-74.0060,
    )

    async_in_memory_session.add(detection_robin)
    async_in_memory_session.add(detection_crow)
    async_in_memory_session.add(detection_cardinal)
    await async_in_memory_session.commit()

    yield async_in_memory_session


@pytest.fixture
def test_config(path_resolver: PathResolver):
    """Should load test configuration from the test config file."""
    manager = ConfigManager(path_resolver)
    return manager.load()


@pytest.fixture(scope="session", autouse=True)
def ensure_redis_running():
    """Ensure Redis is running for tests that require it."""
    # Check if Redis is already running
    try:
        result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=2)
        if result.stdout.strip() == "PONG":
            # Redis is already running
            yield
            return
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Try to start Redis
    try:
        # Start Redis in the background
        subprocess.run(
            ["redis-server", "--daemonize", "yes"], capture_output=True, text=True, check=False
        )

        # Give Redis a moment to start
        time.sleep(0.5)

        # Verify Redis started
        result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=2)
        if result.stdout.strip() == "PONG":
            yield
            return
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Redis is required for tests
    pytest.fail(
        "Redis is not available and could not be started. "
        "Please install and start Redis to run the tests. "
        "Install with: brew install redis (macOS) or apt-get install redis-server (Linux)"
    )


@pytest.fixture(scope="session", autouse=True)
def check_required_assets(repo_root: Path):
    """Check that required assets are available for testing."""
    real_data_dir = repo_root / "data"

    # Map path methods to actual paths for asset checking
    path_map = {
        "get_data_path": real_data_dir,
        "get_models_dir": real_data_dir / "models",
        "get_ioc_database_path": real_data_dir / "database" / "ioc_reference.db",
        "get_avibase_database_path": real_data_dir / "database" / "avibase_database.db",
        "get_patlevin_database_path": real_data_dir / "database" / "patlevin_database.db",
    }

    missing_assets = []

    # Check all required assets using AssetManifest
    for asset in AssetManifest.get_required_assets():
        asset_path = path_map.get(asset.path_method)
        if asset_path is None:
            # Skip assets we don't have paths for
            continue

        # For directories, check if they exist and have content
        if asset.is_directory:
            if not asset_path.exists() or not any(asset_path.glob("*.tflite")):
                missing_assets.append(asset.name)
        else:
            if not asset_path.exists():
                missing_assets.append(asset.name)

    if missing_assets:
        print()
        print("┌" + "─" * 78 + "┐")
        print("│" + " " * 78 + "│")
        print("│  ⚠️  MISSING ASSETS FOR TESTING" + " " * 45 + "│")
        print("│" + " " * 78 + "│")
        print("│  The following required assets are missing for testing:" + " " * 22 + "│")
        for asset in missing_assets:
            spaces_needed = 76 - len(f"│    • {asset}")
            print(f"│    • {asset}" + " " * spaces_needed + "│")
        print("│" + " " * 78 + "│")
        print("│  To run tests with assets, install them first:" + " " * 29 + "│")
        print("│    export BIRDNETPI_DATA=./data" + " " * 43 + "│")
        print("│    uv run install-assets install v2.1.1" + " " * 36 + "│")
        print("│" + " " * 78 + "│")
        print("│  Most tests will still pass without assets (mocked dependencies)." + " " * 9 + "│")
        print(
            "│  Only integration tests and some service tests require real assets." + " " * 10 + "│"
        )
        print("│" + " " * 78 + "│")
        print("└" + "─" * 78 + "┘")
        print()


@pytest.fixture(scope="session")
def model_factory():
    """Create a factory for test model instances.

    This fixture provides a centralized way to create test models with sensible defaults,
    eliminating the need for MagicMock objects that can't be JSON serialized and reducing
    duplication across test files.
    """

    class ModelFactory:
        """Factory class for creating test model instances."""

        @staticmethod
        def create_audio_file(**kwargs: Any) -> AudioFile:
            """Create an AudioFile instance with sensible defaults."""
            defaults = {
                "id": uuid.uuid4(),
                "file_path": Path("/tmp/test_audio.wav"),
                "duration": 3.0,
                "size_bytes": 48000,
            }
            defaults.update(kwargs)
            return AudioFile(**defaults)

        @staticmethod
        def create_detection(**kwargs: Any) -> Detection:
            """Create a Detection instance with sensible defaults."""
            defaults = {
                "id": uuid.uuid4(),
                "species_tensor": "Unknown species_Unknown",
                "scientific_name": "Unknown species",
                "common_name": "Unknown",
                "confidence": 0.5,
                "timestamp": datetime.now(UTC),
                "audio_file_id": None,
                "latitude": 0.0,
                "longitude": 0.0,
                "species_confidence_threshold": 0.1,
                "week": 1,
                "sensitivity_setting": 1.5,
                "overlap": 0.0,
                "weather_timestamp": None,
                "weather_latitude": None,
                "weather_longitude": None,
                "hour_epoch": None,
            }
            defaults.update(kwargs)
            return Detection(**defaults)

        @staticmethod
        def create_detection_with_taxa(**kwargs: Any) -> DetectionWithTaxa:
            """Create a DetectionWithTaxa instance with sensible defaults."""
            defaults = {
                "id": uuid.uuid4(),
                "species_tensor": "Unknown species_Unknown",
                "scientific_name": "Unknown species",
                "common_name": "Unknown",
                "confidence": 0.5,
                "timestamp": datetime.now(UTC),
                "audio_file_id": None,
                "latitude": 0.0,
                "longitude": 0.0,
                "species_confidence_threshold": 0.1,
                "week": 1,
                "sensitivity_setting": 1.5,
                "overlap": 0.0,
                "weather_timestamp": None,
                "weather_latitude": None,
                "weather_longitude": None,
                "hour_epoch": None,
                # DetectionWithTaxa specific fields
                "ioc_english_name": None,
                "translated_name": None,
                "family": None,
                "genus": None,
                "order_name": None,
                "is_first_ever": None,
                "is_first_in_period": None,
                "first_ever_detection": None,
                "first_period_detection": None,
            }
            defaults.update(kwargs)
            return DetectionWithTaxa(**defaults)

        @staticmethod
        def create_weather(**kwargs: Any) -> Weather:
            """Create a Weather instance with sensible defaults."""
            defaults = {
                "timestamp": datetime.now(UTC),
                "latitude": 0.0,
                "longitude": 0.0,
                "source": "test",
                "temperature": 20.0,  # Celsius
                "humidity": 50.0,  # Percentage
                "pressure": 1013.0,  # hPa
                "wind_speed": 10.0,  # km/h
                "wind_direction": 180,  # Degrees
                "precipitation": 0.0,  # mm
                "cloud_cover": 25,  # Percentage
                "weather_code": 0,
                "conditions": "Clear",
            }
            defaults.update(kwargs)
            return Weather(**defaults)

    return ModelFactory()
