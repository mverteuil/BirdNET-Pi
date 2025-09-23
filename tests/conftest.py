from datetime import UTC
from pathlib import Path

import matplotlib
import pytest

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.system.path_resolver import PathResolver

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
    from dependency_injector import providers

    from birdnetpi.config import ConfigManager
    from birdnetpi.web.core.container import Container

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
    from unittest.mock import MagicMock

    mock_cache = MagicMock()
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
    from birdnetpi.web.core.factory import create_app

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
    """Create real in-memory async SQLite session for integration tests.

    This is a global fixture that can be used consistently across all tests
    that need an async SQLAlchemy session for testing.
    """
    from typing import cast

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # Use sessionmaker with class_=AsyncSession which is the standard pattern
    session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create session explicitly to help pyright understand the type
    session = cast(AsyncSession, session_local())
    try:
        # Create test tables if needed
        await session.execute(
            text("""
            CREATE TABLE IF NOT EXISTS test_main (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        )
        await session.commit()
        yield session
    finally:
        await session.close()
        # IMPORTANT: Dispose the engine to prevent file descriptor leaks
        await engine.dispose()


@pytest.fixture
def test_config(path_resolver: PathResolver):
    """Should load test configuration from the test config file."""
    from birdnetpi.config import ConfigManager

    manager = ConfigManager(path_resolver)
    return manager.load()


@pytest.fixture(scope="session", autouse=True)
def ensure_redis_running():
    """Ensure Redis is running for tests that require it."""
    import subprocess
    import time

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
    import os

    from birdnetpi.releases.asset_manifest import AssetManifest
    from birdnetpi.system.path_resolver import PathResolver

    real_data_dir = repo_root / "data"

    stashed_data_dir = os.environ.get("BIRDNETPI_DATA")
    os.environ["BIRDNETPI_DATA"] = str(real_data_dir)

    try:
        path_resolver = PathResolver()
        missing_assets = []

        # Check all required assets using AssetManifest
        for asset in AssetManifest.get_required_assets():
            method = getattr(path_resolver, asset.path_method)
            asset_path = method()

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
            print(
                "│  Most tests will still pass without assets (mocked dependencies)."
                + " " * 9
                + "│"
            )
            print(
                "│  Only integration tests and some service tests require real assets."
                + " " * 10
                + "│"
            )
            print("│" + " " * 78 + "│")
            print("└" + "─" * 78 + "┘")
            print()
    finally:
        # Restore environment
        if stashed_data_dir is not None:
            os.environ["BIRDNETPI_DATA"] = stashed_data_dir
        else:
            os.environ.pop("BIRDNETPI_DATA", None)


@pytest.fixture(scope="session")
def model_factory():
    """Create a factory for test model instances.

    This fixture provides a centralized way to create test models with sensible defaults,
    eliminating the need for MagicMock objects that can't be JSON serialized and reducing
    duplication across test files.
    """
    import uuid
    from datetime import datetime
    from typing import Any

    from birdnetpi.detections.models import AudioFile, Detection, DetectionWithTaxa
    from birdnetpi.location.models import Weather

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
                "temperature_c": 20.0,
                "humidity_percent": 50,
                "pressure_hpa": 1013.0,
                "wind_speed_kmh": 10.0,
                "wind_direction_deg": 180,
                "precipitation_mm": 0.0,
                "cloud_cover_percent": 25,
                "weather_code": 0,
                "description": "Clear",
            }
            defaults.update(kwargs)
            return Weather(**defaults)

    return ModelFactory()
