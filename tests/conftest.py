import asyncio
import inspect
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import matplotlib
import pytest
import redis
import redis.asyncio
from dependency_injector import providers
from sqlalchemy.engine import Result, Row
from sqlalchemy.engine.result import MappingResult, ScalarResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from starlette.testclient import TestClient

from birdnetpi.config import ConfigManager
from birdnetpi.config.models import BirdNETConfig, UpdateConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import AudioFile, Detection, DetectionWithTaxa
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.location.models import Weather
from birdnetpi.releases.asset_manifest import AssetManifest
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.auth import AdminUser, AuthService, pwd_context
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app
from birdnetpi.web.models.detections import DetectionEvent

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")

# Pyleak is available for manual use in tests via @pytest.mark.no_leaks
# The pytest plugin automatically handles this when tests are marked with @pytest.mark.no_leaks


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--blocking-threshold",
        action="store",
        default="0.2",
        help="PyLeak blocking threshold in seconds (default: 0.2)",
    )


def pytest_configure(config):
    """Configure pytest and PyLeak settings."""
    # Read blocking threshold from command line or use default
    threshold = float(config.getoption("--blocking-threshold"))
    # Store in config for PyLeak to use
    config.option.blocking_threshold = threshold


class _AsyncContextManagerProtocol:
    """Protocol for async context manager - used as spec for mocking."""

    async def __aenter__(self):
        """Enter the async context."""
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context."""
        pass


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
       - Wikidata reference database
       - Static files (CSS, JS, images)
       - Templates (HTML templates)
       - Config template (birdnetpi.yaml.template)

    2. Using TEMP paths for WRITABLE data to prevent test pollution:
       - Main database (birdnetpi.db) - prevents tests from writing to data/database/
       - Config file (birdnetpi.yaml) - prevents tests from writing to data/config/
       - Log files - prevents tests from writing to data/logs/
       - Export files - prevents tests from writing to data/exports/

    This separation is critical because:
    - Tests need real assets (models, IOC db, Wikidata db) to function properly
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
    temp_data_dir = tmp_path / "data"
    temp_data_dir.mkdir(parents=True)
    # Override WRITABLE paths to use temp directory
    # IMPORTANT: Override both the attribute AND the method because some code accesses
    # path_resolver.data_dir directly (e.g., RegistryService) while other code calls
    # path_resolver.get_data_dir()
    resolver.data_dir = temp_data_dir
    resolver.get_database_path = lambda: temp_database_dir / "birdnetpi.db"
    resolver.get_birdnetpi_config_path = lambda: temp_config_dir / "birdnetpi.yaml"
    resolver.get_data_dir = lambda: temp_data_dir
    resolver.get_display_simulator_dir = lambda: temp_data_dir / "display-simulator"

    # Keep READ-ONLY paths pointing to real repo locations
    # These are already correct from the base PathResolver, but let's be explicit:
    resolver.get_ioc_database_path = lambda: real_data_dir / "database" / "ioc_reference.db"
    resolver.get_wikidata_database_path = (
        lambda: real_data_dir / "database" / "wikidata_reference.db"
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
    mock_cache.configure_mock(
        **{"get.return_value": None, "set.return_value": True, "ping.return_value": True}
    )
    Container.cache_service.override(providers.Singleton(lambda: mock_cache))

    # Mock the redis client to avoid event loop closure issues during test teardown
    mock_redis = AsyncMock(spec=redis.asyncio.Redis)
    # Mock async methods used by RedisStore
    mock_redis.set = AsyncMock(spec=object, return_value=True)
    mock_redis.get = AsyncMock(spec=object, return_value=None)
    mock_redis.delete = AsyncMock(spec=object, return_value=True)
    mock_redis.close = AsyncMock(spec=object)
    Container.redis_client.override(providers.Singleton(lambda: mock_redis))

    # Mock the auth service to enable authentication in tests
    # Create a test admin user with hashed password "testpassword"
    mock_auth_service = MagicMock(spec=AuthService)
    mock_auth_service.admin_exists.return_value = True
    mock_admin = AdminUser(
        username="admin",
        password_hash=pwd_context.hash("testpassword"),
        created_at=datetime.now(UTC),
    )
    mock_auth_service.load_admin_user.return_value = mock_admin
    mock_auth_service.verify_password.side_effect = lambda plain, hashed: pwd_context.verify(
        plain, hashed
    )
    Container.auth_service.override(providers.Singleton(lambda: mock_auth_service))

    # Reset dependent services to ensure they use the overridden path_resolver
    # These are Singletons that depend on path_resolver and must be recreated
    # with the test path_resolver to prevent permission errors on /var/lib/birdnetpi
    # We reset cached Singleton instances so they get recreated with overridden path_resolver
    try:
        Container.registry_service.reset()
    except AttributeError:
        pass  # Provider might not support reset
    try:
        Container.ebird_region_service.reset()
    except AttributeError:
        pass  # Provider might not support reset

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
    Container.redis_client.reset_override()
    Container.auth_service.reset_override()


@pytest.fixture
def authenticate_sync_client():
    """Provide a function to authenticate a sync TestClient.

    Returns:
        A callable that takes a TestClient and authenticates it

    Example:
        def test_something(authenticate_sync_client):
            client = TestClient(app)
            authenticate_sync_client(client)
    """

    def _authenticate(client: TestClient) -> TestClient:
        login_response = client.post(
            "/admin/login",
            data={"username": "admin", "password": "testpassword"},
            follow_redirects=False,
        )
        assert login_response.status_code == 303  # Successful login redirects
        return client

    return _authenticate


@pytest.fixture
def authenticate_async_client():
    """Provide a function to authenticate an async AsyncClient.

    Returns:
        A callable that takes an AsyncClient and authenticates it

    Example:
        async def test_something(authenticate_async_client):
            async with AsyncClient(...) as client:
                await authenticate_async_client(client)
    """

    async def _authenticate(client):
        login_response = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "testpassword"},
            follow_redirects=False,
        )
        assert login_response.status_code == 303  # Successful login redirects
        return client

    return _authenticate


@pytest.fixture
def authenticated_client(app_with_temp_data, authenticate_sync_client):
    """Create an authenticated test client for routes that require authentication.

    This fixture:
    1. Uses the app_with_temp_data fixture (which mocks AuthService)
    2. Creates a TestClient
    3. Logs in with test credentials (username: admin, password: testpassword)
    4. Returns the authenticated client with session cookie

    Use this fixture for tests that access admin-protected routes.

    Example:
        def test_protected_route(authenticated_client):
            response = authenticated_client.get("/admin/settings")
            assert response.status_code == 200
    """
    with TestClient(app_with_temp_data) as client:
        authenticate_sync_client(client)
        yield client


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


@pytest.fixture
def config_factory():
    """Create a factory for BirdNETConfig instances with sensible defaults.

    This fixture reduces repetitive BirdNETConfig() instantiation across tests
    by providing common configuration patterns and the ability to override
    specific fields as needed.

    Example usage:
        # Default config with all defaults
        config = config_factory()

        # With custom location
        config = config_factory(latitude=42.3601, longitude=-71.0589)

        # Testing mode - high confidence, sensitive audio
        config = config_factory("testing")

        # GPS-enabled field deployment
        config = config_factory("field", enable_gps=True)

        # Webhook testing config
        config = config_factory("webhook", webhook_urls=["http://example.com"])
    """

    def _create_config(preset: str | None = None, **kwargs: Any) -> BirdNETConfig:
        """Create a BirdNETConfig with preset configurations or custom overrides.

        Args:
            preset: Optional preset configuration name. Options:
                - None: Default config with standard settings
                - "minimal": Absolute minimal config (BirdNETConfig())
                - "testing": High thresholds for testing (0.85 confidence, 1.75 sensitivity)
                - "field": Field deployment config with GPS ready
                - "webhook": Config ready for webhook testing
                - "notification": Config with notification rules setup
                - "audio": Audio device testing config
                - "location": Config with custom location (Boston area)
            **kwargs: Override any config field

        Returns:
            BirdNETConfig instance
        """
        presets = {
            "minimal": {},
            "default": {
                "site_name": "Test Site",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "sample_rate": 48000,
                "audio_channels": 1,
            },
            "testing": {
                "site_name": "Testing Site",
                "latitude": 42.3601,
                "longitude": -71.0589,
                "species_confidence_threshold": 0.85,
                "sensitivity_setting": 1.75,
                "sample_rate": 44100,
                "audio_channels": 2,
            },
            "field": {
                "site_name": "Field Deployment",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "enable_gps": False,  # Can be overridden
                "gps_update_interval": 5.0,
            },
            "webhook": {
                "site_name": "Webhook Test",
                "enable_webhooks": True,
                "webhook_urls": [],  # To be populated
                "webhook_events": "detection,health,gps,system",
            },
            "notification": {
                "site_name": "Notification Test",
                "notification_rules": [
                    {
                        "name": "Test Rule",
                        "enabled": True,
                        "service": "webhook",
                        "target": "test_target",
                        "frequency": {"when": "always"},
                        "scope": "all",
                        "minimum_confidence": 0,
                    }
                ],
            },
            "audio": {
                "site_name": "Audio Test",
                "audio_device_index": 0,
                "sample_rate": 48000,
                "audio_channels": 1,
                "audio_overlap": 0.5,
            },
            "location": {
                "site_name": "Location Test",
                "latitude": 42.3601,  # Boston
                "longitude": -71.0589,
                "timezone": "America/New_York",
            },
            "updates": {
                "site_name": "Update Test",
                "updates": UpdateConfig(
                    check_enabled=True,
                    show_banner=True,
                    check_interval_hours=6,
                ),
            },
        }

        # Start with preset or default
        if preset is None:
            config_dict = presets["default"].copy()
        else:
            config_dict = presets.get(preset, presets["default"]).copy()

        # Apply kwargs overrides
        config_dict.update(kwargs)

        return BirdNETConfig(**config_dict)

    return _create_config


@pytest.fixture
def cache():
    """Provide a mock Cache service for tests.

    This fixture provides a properly configured Cache mock that avoids Redis
    connection issues in tests. Individual tests can override specific behaviors
    by setting return_value or side_effect on the mock methods.

    Example:
        def test_something(cache):
            # Use cache with default configuration
            cache.get.return_value = {"key": "value"}
            result = cache.get("test_key")
            assert result == {"key": "value"}
    """
    mock_cache = MagicMock(spec=Cache)
    mock_cache.configure_mock(
        **{"get.return_value": None, "set.return_value": True, "ping.return_value": True}
    )
    return mock_cache


@pytest.fixture(scope="session", autouse=True)
def ensure_redis_running():
    """Ensure Redis is running for tests that require it."""
    # Try to connect to Redis programmatically
    try:
        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        client.ping()
        # Redis is available and responding
        yield
        return
    except (redis.ConnectionError, redis.TimeoutError):
        pass

    # If direct connection failed, try to start Redis locally (for local development)
    try:
        subprocess.run(
            ["redis-server", "--daemonize", "yes"], capture_output=True, text=True, check=False
        )
        time.sleep(0.5)

        # Verify Redis started
        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        client.ping()
        yield
        return
    except (redis.ConnectionError, redis.TimeoutError, FileNotFoundError):
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
        "get_wikidata_database_path": real_data_dir / "database" / "wikidata_reference.db",
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
        print("│    uv run install-assets install latest" + " " * 35 + "│")
        print("│" + " " * 78 + "│")
        print("│  Most tests will still pass without assets (mocked dependencies)." + " " * 9 + "│")
        print(
            "│  Only integration tests and some service tests require real assets." + " " * 10 + "│"
        )
        print("│" + " " * 78 + "│")
        print("└" + "─" * 78 + "┘")
        print()


@pytest.fixture(scope="session")
def model_factory():  # noqa: C901
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

        @staticmethod
        def create_audio_files(count: int, **common_kwargs: Any) -> list[AudioFile]:
            """Create multiple AudioFile instances with common defaults.

            Args:
                count: Number of audio files to create
                **common_kwargs: Common attributes to apply to all audio files

            Returns:
                List of AudioFile instances
            """
            audio_files = []
            for i in range(count):
                kwargs = {
                    "id": uuid.uuid4(),
                    "file_path": Path(f"/tmp/test_audio_{i}.wav"),
                    **common_kwargs,
                }
                audio_files.append(AudioFile(**kwargs))
            return audio_files

        @staticmethod
        def create_detections(count: int, **common_kwargs: Any) -> list[Detection]:
            """Create multiple Detection instances with common defaults.

            Args:
                count: Number of detections to create
                **common_kwargs: Common attributes to apply to all detections

            Returns:
                List of Detection instances
            """
            from datetime import timedelta

            detections = []
            for i in range(count):
                kwargs = {
                    "id": uuid.uuid4(),
                    "timestamp": datetime.now(UTC) - timedelta(hours=i),
                    **common_kwargs,
                }
                detections.append(Detection(**kwargs))
            return detections

        @staticmethod
        def create_detections_with_taxa(
            count: int, **common_kwargs: Any
        ) -> list[DetectionWithTaxa]:
            """Create multiple DetectionWithTaxa instances with common defaults.

            Args:
                count: Number of detections to create
                **common_kwargs: Common attributes to apply to all detections

            Returns:
                List of DetectionWithTaxa instances
            """
            from datetime import timedelta

            detections = []
            for i in range(count):
                kwargs = {
                    "id": uuid.uuid4(),
                    "timestamp": datetime.now(UTC) - timedelta(hours=i),
                    **common_kwargs,
                }
                detections.append(DetectionWithTaxa(**kwargs))
            return detections

    return ModelFactory()


@pytest.fixture
def detection_event_factory():
    """Create a factory for DetectionEvent instances with sensible defaults.

    This fixture provides a centralized way to create DetectionEvent instances
    for testing, reducing boilerplate in tests that need to create multiple events.
    """

    def _create_detection_event(**kwargs: Any) -> DetectionEvent:
        """Create a DetectionEvent instance with defaults."""
        defaults = {
            "species_tensor": "Unknown species_Unknown",
            "scientific_name": "Unknown species",
            "common_name": "Unknown",
            "confidence": 0.5,
            "timestamp": datetime.now(UTC),
            "audio_data": "",  # Base64 encoded audio
            "sample_rate": 48000,
            "channels": 1,
            "latitude": 0.0,
            "longitude": 0.0,
            "species_confidence_threshold": 0.1,
            "week": 1,
            "sensitivity_setting": 1.5,
            "overlap": 0.0,
        }
        defaults.update(kwargs)
        return DetectionEvent(**defaults)

    return _create_detection_event


@pytest.fixture
def mock_services_factory():
    """Create a factory for common mock service configurations.

    This fixture provides properly configured mock services to reduce
    repetitive mock setup code across test files.
    """

    def _create_mock_services(**overrides: Any) -> dict[str, Any]:
        """Create dictionary of common mock services.

        Args:
            **overrides: Service overrides (e.g., database_service=my_custom_mock)

        Returns:
            Dictionary mapping service names to mock instances
        """
        defaults = {
            "database_service": MagicMock(spec=CoreDatabaseService),
            "species_database": MagicMock(spec=SpeciesDatabaseService),
            "species_display_service": MagicMock(spec=SpeciesDisplayService),
            "detection_query_service": MagicMock(spec=DetectionQueryService),
            "file_manager": MagicMock(spec=FileManager),
        }
        defaults.update(overrides)
        return defaults

    return _create_mock_services


@pytest.fixture
def service_bundle_factory(mock_services_factory):
    """Create common service bundles with preset configurations.

    This fixture reduces repetitive service mock setup by providing common
    bundles of services used together in different parts of the application.

    Example:
        def test_analytics_feature(service_bundle_factory):
            services = service_bundle_factory("analytics")
            # Get configured services
            db = services["database_service"]
            query = services["detection_query_service"]
            display = services["species_display_service"]
    """

    def _create_bundle(bundle_type: str = "standard", **overrides: Any) -> dict[str, Any]:
        """Create a service bundle with common configurations.

        Args:
            bundle_type: Type of bundle ("standard", "analytics", "minimal")
            **overrides: Individual service overrides

        Returns:
            Dictionary of configured mock services
        """
        bundles = {
            "standard": {
                "include_database": True,
                "include_species_db": True,
                "include_query_service": True,
                "include_file_manager": False,
                "include_display_service": False,
            },
            "analytics": {
                "include_database": True,
                "include_species_db": True,
                "include_query_service": True,
                "include_display_service": True,
                "include_file_manager": False,
            },
            "minimal": {
                "include_database": True,
                "include_species_db": False,
                "include_query_service": False,
                "include_file_manager": False,
                "include_display_service": False,
            },
            "file_ops": {
                "include_database": True,
                "include_species_db": False,
                "include_query_service": False,
                "include_file_manager": True,
                "include_display_service": False,
            },
        }

        config = bundles.get(bundle_type, bundles["standard"]).copy()

        # Build service dictionary based on config
        services = {}
        if config["include_database"]:
            services["database_service"] = overrides.get(
                "database_service", MagicMock(spec=CoreDatabaseService)
            )
        if config["include_species_db"]:
            services["species_database"] = overrides.get(
                "species_database", MagicMock(spec=SpeciesDatabaseService)
            )
        if config["include_query_service"]:
            services["detection_query_service"] = overrides.get(
                "detection_query_service", MagicMock(spec=DetectionQueryService)
            )
        if config["include_display_service"]:
            services["species_display_service"] = overrides.get(
                "species_display_service", MagicMock(spec=SpeciesDisplayService)
            )
        if config["include_file_manager"]:
            services["file_manager"] = overrides.get("file_manager", MagicMock(spec=FileManager))

        return services

    return _create_bundle


@pytest.fixture
def async_mock_factory():
    """Create a factory for properly configured async mocks.

    This fixture helps avoid the common mistake of using MagicMock
    for async methods, which doesn't work properly with await.
    """

    def _create_async_mock(spec: type, **return_values: Any) -> MagicMock:
        """Create a mock with AsyncMock for async methods.

        Args:
            spec: The class to spec the mock against
            **return_values: Mapping of method names to return values

        Returns:
            Properly configured mock instance
        """
        mock = MagicMock(spec=spec)

        # Configure return values with appropriate mock type
        for attr_name, return_value in return_values.items():
            # Check if the attribute is a coroutine function
            spec_attr = getattr(spec, attr_name, None)
            if spec_attr and (
                asyncio.iscoroutinefunction(spec_attr) or inspect.iscoroutinefunction(spec_attr)
            ):
                # AsyncMock for async method - no spec needed as it replaces a single method
                setattr(mock, attr_name, AsyncMock(return_value=return_value))  # ast-grep-ignore
            else:
                # Regular method/property
                if callable(return_value):
                    setattr(mock, attr_name, return_value)
                else:
                    getattr(mock, attr_name).return_value = return_value

        return mock

    return _create_async_mock


@pytest.fixture
def db_session_factory():
    """Create a factory for database session mocks with common configurations.

    This fixture eliminates the repetitive pattern of creating AsyncSession,
    Result, and context manager mocks that appears throughout the test suite.

    Example:
        def test_query(db_session_factory):
            session, result = db_session_factory(
                fetch_results=[{"scientific_name": "Species1", "count": 50}]
            )

            # Session is already configured with execute returning result
            query_result = await session.execute(select(Detection))
            rows = query_result.fetchall()
            assert rows[0]["scientific_name"] == "Species1"
    """

    def _create_session(
        fetch_results: list[Any] | None = None,
        scalar_result: Any = None,
        side_effect: Any = None,
        mappings_result: list[dict[str, Any]] | None = None,
    ) -> tuple[AsyncMock, MagicMock]:
        """Create configured database session and result mocks.

        Args:
            fetch_results: List of results for fetchall()/fetchone()
            scalar_result: Result for session.scalar() - configured on session directly
            side_effect: Side effect for session.execute()
            mappings_result: List of dicts for result.mappings().all()

        Returns:
            Tuple of (session_mock, result_mock)
        """
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock(spec=Result)

        # Configure fetch methods on result
        if fetch_results is not None:
            result.fetchall.return_value = fetch_results
            result.fetchone.return_value = fetch_results[0] if fetch_results else None
            result.all.return_value = fetch_results

        # Configure scalar methods - both on result and session
        # Note: always configure even if scalar_result is None (to return None instead of MagicMock)
        result.scalar_one_or_none.return_value = scalar_result
        result.scalar.return_value = scalar_result
        # Also configure session.scalar() directly for queries that use it
        session.scalar.return_value = scalar_result

        # Configure mappings
        if mappings_result is not None:
            mappings_mock = MagicMock(spec=MappingResult)
            mappings_mock.all.return_value = mappings_result
            result.mappings.return_value = mappings_mock

        # Configure scalars (for result.scalars().all() pattern)
        # Always configure to return proper object even when fetch_results is None
        scalars_mock = MagicMock(spec=ScalarResult)
        scalars_mock.all.return_value = fetch_results if fetch_results is not None else []
        scalars_mock.fetchall.return_value = fetch_results if fetch_results is not None else []
        scalars_mock.first.return_value = fetch_results[0] if fetch_results else None
        scalars_mock.one_or_none.return_value = (
            fetch_results[0] if fetch_results and len(fetch_results) == 1 else None
        )
        result.scalars.return_value = scalars_mock

        # Configure session.execute behavior
        if side_effect:
            session.execute.side_effect = side_effect
        else:
            session.execute.return_value = result

        return session, result

    return _create_session


@pytest.fixture
def db_service_factory(db_session_factory):
    """Create a factory for CoreDatabaseService mocks with context manager support.

    This fixture builds on db_session_factory to provide a fully configured
    CoreDatabaseService mock with proper async context manager support.

    Example:
        def test_database_operation(db_service_factory):
            service, session, result = db_service_factory(
                session_config={"fetch_results": [detection1, detection2]}
            )

            # Service is ready to use with get_async_db()
            async with service.get_async_db() as db:
                query_result = await db.execute(select(Detection))
                detections = query_result.fetchall()
                assert len(detections) == 2
    """

    def _create_service(
        session_config: dict[str, Any] | None = None,
    ) -> tuple[MagicMock, AsyncMock, MagicMock]:
        """Create configured CoreDatabaseService mock.

        Args:
            session_config: Configuration dict for db_session_factory

        Returns:
            Tuple of (service_mock, session_mock, result_mock)
        """
        # Create session with provided configuration
        session, result = db_session_factory(**(session_config or {}))

        # Create service mock
        service = MagicMock(spec=CoreDatabaseService)

        # Configure context manager
        context = AsyncMock(spec=_AsyncContextManagerProtocol)
        context.__aenter__.return_value = session
        context.__aexit__.return_value = None
        service.get_async_db.return_value = context

        # Add async_engine mock for completeness
        service.async_engine = AsyncMock(spec=AsyncEngine)

        return service, session, result

    return _create_service


@pytest.fixture
def detection_query_service_factory():
    """Create a factory for DetectionQueryService mocks with common query methods.

    This fixture eliminates repetitive setup of DetectionQueryService async methods
    that appears frequently in analytics and detection tests.

    Example:
        def test_analytics(detection_query_service_factory):
            service = detection_query_service_factory(
                species_counts=[{"scientific_name": "Species1", "count": 50}],
                detection_count=100,
                unique_species_count=25
            )

            counts = await service.get_species_counts()
            assert counts[0]["count"] == 50
    """

    def _create_service(
        species_counts: list[dict[str, Any]] | None = None,
        hourly_counts: list[dict[str, Any]] | None = None,
        detection_count: int | None = None,
        unique_species_count: int | None = None,
        **extra_methods: Any,
    ) -> MagicMock:
        """Create configured DetectionQueryService mock.

        Args:
            species_counts: Return value for get_species_counts()
            hourly_counts: Return value for get_hourly_counts()
            detection_count: Return value for get_detection_count()
            unique_species_count: Return value for get_unique_species_count()
            **extra_methods: Additional method configurations

        Returns:
            Configured DetectionQueryService mock
        """
        service = MagicMock(spec=DetectionQueryService)

        # Configure common async query methods
        if species_counts is not None:
            service.get_species_counts = AsyncMock(
                spec=DetectionQueryService.get_species_counts, return_value=species_counts
            )

        if hourly_counts is not None:
            service.get_hourly_counts = AsyncMock(
                spec=DetectionQueryService.get_hourly_counts, return_value=hourly_counts
            )

        if detection_count is not None:
            service.get_detection_count = AsyncMock(
                spec=DetectionQueryService.get_detection_count, return_value=detection_count
            )

        if unique_species_count is not None:
            service.get_unique_species_count = AsyncMock(
                spec=DetectionQueryService.get_unique_species_count,
                return_value=unique_species_count,
            )

        # Configure any additional methods
        for method_name, return_value in extra_methods.items():
            # Get the method from DetectionQueryService for spec if it exists
            method_spec = getattr(DetectionQueryService, method_name, None)
            setattr(service, method_name, AsyncMock(spec=method_spec, return_value=return_value))

        return service

    return _create_service


@pytest.fixture
def row_factory():
    """Create a factory for database Row mocks from dictionaries.

    This fixture simplifies creating mock database query results by converting
    dictionaries into Row-like objects with attribute access.

    Example:
        def test_query_results(row_factory):
            rows = row_factory([
                {"scientific_name": "Species1", "count": 50},
                {"scientific_name": "Species2", "count": 30},
            ])

            assert rows[0].scientific_name == "Species1"
            assert rows[1].count == 30
    """

    def _create_rows(data_dicts: list[dict[str, Any]]) -> list[MagicMock]:
        """Create mock Row objects from dictionaries.

        Args:
            data_dicts: List of dictionaries with row data

        Returns:
            List of mock Row objects with attributes set from dict keys
        """
        rows = []
        for data in data_dicts:
            row = MagicMock(spec=Row)
            for key, value in data.items():
                setattr(row, key, value)
            rows.append(row)
        return rows

    return _create_rows


@pytest.fixture
def httpx_client_factory():
    """Create a factory for httpx.AsyncClient mocks with common configurations.

    This fixture eliminates repetitive httpx.AsyncClient mock creation
    that appears in webhook and HTTP client tests.

    Example:
        def test_webhook_request(httpx_client_factory):
            client = httpx_client_factory(
                post_response={"status_code": 200, "text": "OK"}
            )

            # Client is already configured
            response = await client.post("https://example.com", json={})
            assert response.status_code == 200
    """

    def _create_client(
        post_response: dict[str, Any] | None = None,
        get_response: dict[str, Any] | None = None,
        post_side_effect: Any = None,
        get_side_effect: Any = None,
    ) -> MagicMock:
        """Create configured httpx.AsyncClient mock.

        Args:
            post_response: Dict with status_code, text, json for POST responses
            get_response: Dict with status_code, text, json for GET responses
            post_side_effect: Side effect for post() method
            get_side_effect: Side effect for get() method

        Returns:
            Configured httpx.AsyncClient mock
        """
        import httpx

        client = MagicMock(spec=httpx.AsyncClient)

        # Configure aclose for cleanup
        client.aclose = AsyncMock(spec=httpx.AsyncClient.aclose)

        # Configure POST method
        if post_response is not None:
            response = MagicMock(spec=httpx.Response)
            response.status_code = post_response.get("status_code", 200)
            response.text = post_response.get("text", "")
            if "json" in post_response:
                response.json.return_value = post_response["json"]
            client.post.return_value = response
        elif post_side_effect is not None:
            client.post.side_effect = post_side_effect

        # Configure GET method
        if get_response is not None:
            response = MagicMock(spec=httpx.Response)
            response.status_code = get_response.get("status_code", 200)
            response.text = get_response.get("text", "")
            if "json" in get_response:
                response.json.return_value = get_response["json"]
            client.get.return_value = response
        elif get_side_effect is not None:
            client.get.side_effect = get_side_effect

        return client

    return _create_client
