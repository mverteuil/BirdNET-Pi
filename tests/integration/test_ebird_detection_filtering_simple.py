"""Simplified integration tests for eBird detection filtering.

This module focuses on key end-to-end scenarios, while unit tests in
test_ebird.py and test_cleanup.py provide comprehensive edge case coverage.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from birdnetpi.config.manager import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.releases.registry_service import BoundingBox, RegionPackInfo, RegistryService
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


def create_detection_payload(**overrides):
    """Create a valid detection event payload with defaults."""
    defaults = {
        "species_tensor": "Unknown species_Unknown",
        "scientific_name": "Unknown species",
        "common_name": "Unknown",
        "confidence": 0.95,
        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
        "audio_data": "",  # Base64 encoded audio (empty for tests)
        "sample_rate": 48000,
        "channels": 1,
        "latitude": 43.6532,
        "longitude": -79.3832,
        "species_confidence_threshold": 0.1,
        "week": 1,
        "sensitivity_setting": 1.5,
        "overlap": 0.0,
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
def mock_ebird_service():
    """Create mock eBird service with configurable tier responses."""
    mock_service = MagicMock(spec=EBirdRegionService)
    mock_service.attach_to_session = AsyncMock(spec=object)
    mock_service.detach_from_session = AsyncMock(spec=object)

    # Store reference for tests to configure behavior
    mock_service._confidence_tiers = {}

    # Use AsyncMock to properly intercept the async method
    async def get_tier(session, scientific_name, h3_cell):
        return mock_service._confidence_tiers.get(scientific_name)

    mock_service.get_species_confidence_tier = AsyncMock(spec=object, side_effect=get_tier)

    return mock_service


@pytest.fixture
async def app_with_ebird_filtering(mock_ebird_service, path_resolver, tmp_path):
    """FastAPI app with eBird filtering enabled and mocked eBird service.

    IMPORTANT: We override Container providers BEFORE creating the app
    so that the mocked registry service is used when the app is initialized.
    """
    # Override Container providers BEFORE creating app
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))

    # Create test config
    manager = ConfigManager(path_resolver)
    test_config = manager.load()

    # Enable eBird filtering in config
    test_config.ebird_filtering.enabled = True
    test_config.ebird_filtering.detection_mode = "filter"
    test_config.ebird_filtering.detection_strictness = "vagrant"
    test_config.ebird_filtering.h3_resolution = 5
    test_config.ebird_filtering.unknown_species_behavior = "allow"

    Container.config.override(providers.Singleton(lambda: test_config))

    # Create test database service
    temp_db_service = CoreDatabaseService(path_resolver.get_database_path())
    await temp_db_service.initialize()
    Container.core_database.override(providers.Singleton(lambda: temp_db_service))

    # Mock cache service
    mock_cache = MagicMock(spec=Cache)
    mock_cache.configure_mock(
        **{"get.return_value": None, "set.return_value": True, "ping.return_value": True}
    )
    Container.cache_service.override(providers.Singleton(lambda: mock_cache))

    # Override the eBird service in the container BEFORE creating app
    Container.ebird_region_service.override(providers.Singleton(lambda: mock_ebird_service))

    # Create mock registry service that returns the real pack info for CI
    # CI installs "north-america-great-lakes" region pack
    mock_registry_service = MagicMock(spec=RegistryService)
    mock_registry_service.find_pack_for_coordinates.return_value = RegionPackInfo(
        region_id="north-america-great-lakes",
        release_name="north-america-great-lakes",
        h3_cells=[],
        pack_count=1,
        total_size_mb=1.0,
        resolution=5,
        center={"lat": 43.6532, "lon": -79.3832},  # Toronto area
        bbox=BoundingBox(min_lat=40.0, max_lat=50.0, min_lon=-90.0, max_lon=-70.0),
        download_url=None,
    )
    Container.registry_service.override(providers.Singleton(lambda: mock_registry_service))

    # Reset dependent services
    try:
        Container.ebird_region_service.reset()
    except AttributeError:
        pass
    try:
        Container.registry_service.reset()
    except AttributeError:
        pass

    # NOW create the app with our overridden providers
    app = create_app()

    # Store references
    app._test_db_service = temp_db_service  # type: ignore[attr-defined]
    app._mock_ebird_service = mock_ebird_service  # type: ignore[attr-defined]

    yield app

    # Clean up
    if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
        await temp_db_service.async_engine.dispose()

    Container.path_resolver.reset_override()
    Container.database_path.reset_override()
    Container.config.reset_override()
    Container.core_database.reset_override()
    Container.cache_service.reset_override()
    Container.ebird_region_service.reset_override()
    Container.registry_service.reset_override()


class TestEBirdFilteringIntegration:
    """Integration tests for eBird filtering end-to-end flows."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_vagrant_species_blocked_in_filter_mode(
        self, app_with_ebird_filtering, authenticate_async_client
    ):
        """Should block vagrant species when filtering is enabled."""
        # Configure mock to return vagrant tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Turdus migratorius"] = "vagrant"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            await authenticate_async_client(client)
            response = await client.post(
                "/api/detections/",
                json=create_detection_payload(
                    species_tensor="Turdus migratorius_American Robin",
                    scientific_name="Turdus migratorius",
                    common_name="American Robin",
                ),
            )

            assert response.status_code == 201
            data = response.json()
            # Detection should be filtered (no ID)
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_common_species_allowed(
        self, app_with_ebird_filtering, authenticate_async_client
    ):
        """Should allow common species regardless of strictness."""
        # Configure mock to return common tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Cyanocitta cristata"] = "common"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            await authenticate_async_client(client)
            response = await client.post(
                "/api/detections/",
                json=create_detection_payload(
                    species_tensor="Cyanocitta cristata_Blue Jay",
                    scientific_name="Cyanocitta cristata",
                    common_name="Blue Jay",
                ),
            )

            assert response.status_code == 201
            data = response.json()
            # Detection should be created
            assert data["detection_id"] is not None

    async def test_filtering_disabled(self, app_with_temp_data, authenticate_async_client):
        """Should allow all detections when filtering is disabled."""
        # Ensure filtering is disabled
        config = Container.config()
        config.ebird_filtering.enabled = False

        async with AsyncClient(
            transport=ASGITransport(app=app_with_temp_data), base_url="http://test"
        ) as client:
            await authenticate_async_client(client)
            response = await client.post(
                "/api/detections/",
                json=create_detection_payload(
                    species_tensor="Turdus migratorius_American Robin",
                    scientific_name="Turdus migratorius",
                    common_name="American Robin",
                ),
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_unknown_species_behavior(
        self, app_with_ebird_filtering, authenticate_async_client
    ):
        """Should handle unknown species according to configuration."""
        # Mock service returns None (species not found)
        # Config has unknown_species_behavior = "allow" by default

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            await authenticate_async_client(client)
            response = await client.post(
                "/api/detections/",
                json=create_detection_payload(
                    species_tensor="Unknown species_Unknown",
                    scientific_name="Unknown species",
                    common_name="Unknown",
                ),
            )

            assert response.status_code == 201
            data = response.json()
            # Should be allowed (unknown_species_behavior = "allow")
            assert data["detection_id"] is not None

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_warn_mode_creates_detection(
        self, app_with_ebird_filtering, authenticate_async_client
    ):
        """Should create detection in warn mode even when species would be filtered."""
        # Set mode to warn
        config = Container.config()
        config.ebird_filtering.detection_mode = "warn"

        # Configure mock to return vagrant tier (would be blocked in filter mode)
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Turdus migratorius"] = "vagrant"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            await authenticate_async_client(client)
            response = await client.post(
                "/api/detections/",
                json=create_detection_payload(
                    species_tensor="Turdus migratorius_American Robin",
                    scientific_name="Turdus migratorius",
                    common_name="American Robin",
                ),
            )

            assert response.status_code == 201
            data = response.json()
            # Should still create detection in warn mode
            assert data["detection_id"] is not None
