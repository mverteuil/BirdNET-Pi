"""Integration tests for eBird regional confidence filtering at detection time.

This module tests the complete flow of eBird filtering from API endpoint through
to the database, including all filtering modes, strictness levels, and edge cases.
"""

from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.releases.registry_service import BoundingBox, RegionPackInfo, RegistryService
from birdnetpi.web.core.container import Container


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
    mock_service.attach_to_session = AsyncMock(spec=Awaitable[Any])
    mock_service.detach_from_session = AsyncMock(spec=Awaitable[Any])

    # Store reference for tests to configure behavior
    mock_service._confidence_tiers = {}

    async def get_tier(session, scientific_name, h3_cell):
        return mock_service._confidence_tiers.get(scientific_name)

    mock_service.get_species_confidence_tier = get_tier

    return mock_service


@pytest.fixture
async def app_with_ebird_filtering(app_with_temp_data, mock_ebird_service, tmp_path):
    """FastAPI app with eBird filtering enabled and mocked eBird service."""
    # Create mock eBird pack database file
    ebird_dir = tmp_path / "database" / "ebird_packs"
    ebird_dir.mkdir(parents=True, exist_ok=True)
    pack_db = ebird_dir / "test-pack-2025.08.db"
    pack_db.touch()

    # Get the path resolver from container
    path_resolver = Container.path_resolver()

    # Override path resolver to return test pack path
    original_get_ebird_pack_path = path_resolver.get_ebird_pack_path
    path_resolver.get_ebird_pack_path = lambda region_pack_name: pack_db

    # Override the eBird service in the container
    Container.ebird_region_service.override(providers.Singleton(lambda: mock_ebird_service))

    # Create mock registry service that returns test pack info
    mock_registry_service = MagicMock(spec=RegistryService)
    mock_registry_service.find_pack_for_coordinates.return_value = RegionPackInfo(
        region_id="test-pack",
        release_name="test-pack-2025.08",
        h3_cells=[],
        pack_count=1,
        total_size_mb=1.0,
        resolution=5,
        center={"lat": 40.7128, "lon": -74.0060},
        bbox=BoundingBox(min_lat=40.0, max_lat=41.0, min_lon=-75.0, max_lon=-73.0),
        download_url=None,
    )
    Container.registry_service.override(providers.Singleton(lambda: mock_registry_service))

    # Update config to enable eBird filtering
    config = Container.config()
    config.ebird_filtering.enabled = True
    config.ebird_filtering.detection_mode = "filter"
    config.ebird_filtering.detection_strictness = "vagrant"
    config.ebird_filtering.h3_resolution = 5
    config.ebird_filtering.unknown_species_behavior = "allow"

    # Store reference to mock service for test configuration
    app_with_temp_data._mock_ebird_service = mock_ebird_service

    yield app_with_temp_data

    # Clean up
    Container.ebird_region_service.reset_override()
    Container.registry_service.reset_override()
    path_resolver.get_ebird_pack_path = original_get_ebird_pack_path


class TestEBirdFilteringDisabled:
    """Test that detections are allowed when eBird filtering is disabled."""

    async def test_detection_allowed_when_filtering_disabled(self, app_with_temp_data):
        """Should allow detection when eBird filtering is disabled."""
        # Ensure filtering is disabled
        config = Container.config()
        config.ebird_filtering.enabled = False

        async with AsyncClient(
            transport=ASGITransport(app=app_with_temp_data), base_url="http://test"
        ) as client:
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
            assert "filtered" not in data["message"].lower()


class TestEBirdFilteringModeOff:
    """Test that detections are allowed when mode is 'off'."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_detection_allowed_when_mode_off(self, app_with_ebird_filtering):
        """Should allow detection when detection_mode is 'off'."""
        # Set mode to off
        config = Container.config()
        config.ebird_filtering.detection_mode = "off"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None


class TestEBirdFilteringWarnMode:
    """Test that detections are logged but allowed in 'warn' mode."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_vagrant_species_warned_but_allowed(self, app_with_ebird_filtering):
        """Should warn about vagrant species but still create detection."""
        # Set mode to warn
        config = Container.config()
        config.ebird_filtering.detection_mode = "warn"
        config.ebird_filtering.detection_strictness = "vagrant"

        # Configure mock to return vagrant tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Turdus migratorius"] = "vagrant"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            # Should still create detection in warn mode
            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None


class TestEBirdFilteringFilterMode:
    """Test that detections are blocked in 'filter' mode."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_vagrant_species_blocked_with_vagrant_strictness(self, app_with_ebird_filtering):
        """Should block vagrant species with vagrant strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "vagrant"

        # Configure mock to return vagrant tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Turdus migratorius"] = "vagrant"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_rare_species_blocked_with_rare_strictness(self, app_with_ebird_filtering):
        """Should block rare species with rare strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "rare"

        # Configure mock to return rare tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Corvus brachyrhynchos"] = "rare"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Corvus brachyrhynchos",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()

    async def test_uncommon_species_blocked_with_uncommon_strictness(
        self, app_with_ebird_filtering
    ):
        """Should block uncommon species with uncommon strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "uncommon"

        # Configure mock to return uncommon tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Cardinalis cardinalis"] = "uncommon"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Cardinalis cardinalis",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_common_species_allowed_with_all_strictness(self, app_with_ebird_filtering):
        """Should allow common species with any strictness level."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"

        # Configure mock to return common tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Cyanocitta cristata"] = "common"

        for strictness in ["vagrant", "rare", "uncommon", "common"]:
            config.ebird_filtering.detection_strictness = strictness

            async with AsyncClient(
                transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/detections/",
                    json={
                        "species_tensor": "Cyanocitta cristata",
                        "confidence": 0.95,
                        "latitude": 43.6532,
                        "longitude": -79.3832,
                        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                    },
                )

                assert response.status_code == 201
                data = response.json()
                assert data["detection_id"] is not None, f"Failed for strictness={strictness}"


class TestEBirdFilteringUnknownSpecies:
    """Test handling of species not found in eBird data."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_unknown_species_allowed_with_allow_behavior(self, app_with_ebird_filtering):
        """Should allow unknown species when behavior is 'allow'."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.unknown_species_behavior = "allow"

        # Mock service returns None (species not found)
        # This is the default behavior

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Unknown species",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_unknown_species_blocked_with_block_behavior(self, app_with_ebird_filtering):
        """Should block unknown species when behavior is 'block'."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.unknown_species_behavior = "block"

        # Mock service returns None (species not found)

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Unknown species",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()


class TestEBirdFilteringWithoutCoordinates:
    """Test that filtering is skipped when coordinates are missing."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_detection_allowed_without_latitude(self, app_with_ebird_filtering):
        """Should allow detection when latitude is missing."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_detection_allowed_without_longitude(self, app_with_ebird_filtering):
        """Should allow detection when longitude is missing."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None


class TestEBirdFilteringErrorHandling:
    """Test error handling in eBird filtering."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_detection_allowed_on_ebird_service_error(self, app_with_ebird_filtering):
        """Should allow detection if eBird service fails."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"

        # Configure mock to raise exception
        mock_service = app_with_ebird_filtering._mock_ebird_service

        async def failing_attach(*args, **kwargs):
            raise Exception("Database error")

        mock_service.attach_to_session = failing_attach

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/detections/",
                json={
                    "species_tensor": "Turdus migratorius",
                    "confidence": 0.95,
                    "latitude": 43.6532,
                    "longitude": -79.3832,
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                },
            )

            # Should still create detection despite error
            assert response.status_code == 201
            data = response.json()
            assert data["detection_id"] is not None


class TestEBirdFilteringStrictnessLevels:
    """Test that strictness levels correctly filter species."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_vagrant_strictness_allows_rare_uncommon_common(self, app_with_ebird_filtering):
        """Should only block vagrant species with vagrant strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "vagrant"

        mock_service = app_with_ebird_filtering._mock_ebird_service

        # Test all tiers
        tiers_and_expected = [
            ("vagrant", None),  # Blocked
            ("rare", "id"),  # Allowed
            ("uncommon", "id"),  # Allowed
            ("common", "id"),  # Allowed
        ]

        for tier, expected_id in tiers_and_expected:
            mock_service._confidence_tiers["Test species"] = tier

            async with AsyncClient(
                transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/detections/",
                    json={
                        "species_tensor": "Test species",
                        "confidence": 0.95,
                        "latitude": 43.6532,
                        "longitude": -79.3832,
                        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                    },
                )

                assert response.status_code == 201
                data = response.json()
                if expected_id:
                    assert data["detection_id"] is not None, f"Failed for tier={tier}"
                else:
                    assert data["detection_id"] is None, f"Failed for tier={tier}"

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_rare_strictness_allows_uncommon_common(self, app_with_ebird_filtering):
        """Should block vagrant and rare species with rare strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "rare"

        mock_service = app_with_ebird_filtering._mock_ebird_service

        tiers_and_expected = [
            ("vagrant", None),  # Blocked
            ("rare", None),  # Blocked
            ("uncommon", "id"),  # Allowed
            ("common", "id"),  # Allowed
        ]

        for tier, expected_id in tiers_and_expected:
            mock_service._confidence_tiers["Test species"] = tier

            async with AsyncClient(
                transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/detections/",
                    json={
                        "species_tensor": "Test species",
                        "confidence": 0.95,
                        "latitude": 43.6532,
                        "longitude": -79.3832,
                        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                    },
                )

                assert response.status_code == 201
                data = response.json()
                if expected_id:
                    assert data["detection_id"] is not None, f"Failed for tier={tier}"
                else:
                    assert data["detection_id"] is None, f"Failed for tier={tier}"

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_uncommon_strictness_allows_only_common(self, app_with_ebird_filtering):
        """Should only allow common species with uncommon strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "uncommon"

        mock_service = app_with_ebird_filtering._mock_ebird_service

        tiers_and_expected = [
            ("vagrant", None),  # Blocked
            ("rare", None),  # Blocked
            ("uncommon", None),  # Blocked
            ("common", "id"),  # Allowed
        ]

        for tier, expected_id in tiers_and_expected:
            mock_service._confidence_tiers["Test species"] = tier

            async with AsyncClient(
                transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/detections/",
                    json={
                        "species_tensor": "Test species",
                        "confidence": 0.95,
                        "latitude": 43.6532,
                        "longitude": -79.3832,
                        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                    },
                )

                assert response.status_code == 201
                data = response.json()
                if expected_id:
                    assert data["detection_id"] is not None, f"Failed for tier={tier}"
                else:
                    assert data["detection_id"] is None, f"Failed for tier={tier}"

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_common_strictness_allows_only_common(self, app_with_ebird_filtering):
        """Should only allow common species with common strictness."""
        config = Container.config()
        config.ebird_filtering.detection_mode = "filter"
        config.ebird_filtering.detection_strictness = "common"

        mock_service = app_with_ebird_filtering._mock_ebird_service

        tiers_and_expected = [
            ("vagrant", None),  # Blocked
            ("rare", None),  # Blocked
            ("uncommon", None),  # Blocked
            ("common", "id"),  # Allowed
        ]

        for tier, expected_id in tiers_and_expected:
            mock_service._confidence_tiers["Test species"] = tier

            async with AsyncClient(
                transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/detections/",
                    json={
                        "species_tensor": "Test species",
                        "confidence": 0.95,
                        "latitude": 43.6532,
                        "longitude": -79.3832,
                        "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
                    },
                )

                assert response.status_code == 201
                data = response.json()
                if expected_id:
                    assert data["detection_id"] is not None, f"Failed for tier={tier}"
                else:
                    assert data["detection_id"] is None, f"Failed for tier={tier}"
