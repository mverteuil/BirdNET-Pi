"""Simplified integration tests for eBird detection filtering.

This module focuses on key end-to-end scenarios, while unit tests in
test_ebird.py and test_cleanup.py provide comprehensive edge case coverage.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from birdnetpi.database.ebird import EBirdRegionService
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

    def mock_get_ebird_pack_path(region_pack_name: str):
        return pack_db

    path_resolver.get_ebird_pack_path = mock_get_ebird_pack_path

    # Override the eBird service in the container
    Container.ebird_region_service.override(providers.Singleton(lambda: mock_ebird_service))

    # Update config to enable eBird filtering
    config = Container.config()
    config.ebird_filtering.enabled = True
    config.ebird_filtering.detection_mode = "filter"
    config.ebird_filtering.detection_strictness = "vagrant"
    config.ebird_filtering.region_pack = "test-pack-2025.08"
    config.ebird_filtering.h3_resolution = 5
    config.ebird_filtering.unknown_species_behavior = "allow"

    # Store reference to mock service for test configuration
    app_with_temp_data._mock_ebird_service = mock_ebird_service

    yield app_with_temp_data

    # Clean up
    Container.ebird_region_service.reset_override()
    path_resolver.get_ebird_pack_path = original_get_ebird_pack_path


class TestEBirdFilteringIntegration:
    """Integration tests for eBird filtering end-to-end flows."""

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_vagrant_species_blocked_in_filter_mode(self, app_with_ebird_filtering):
        """Should block vagrant species when filtering is enabled."""
        # Configure mock to return vagrant tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Turdus migratorius"] = "vagrant"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
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
            # Detection should be filtered (no ID)
            assert data["detection_id"] is None
            assert "filtered" in data["message"].lower()

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_common_species_allowed(self, app_with_ebird_filtering):
        """Should allow common species regardless of strictness."""
        # Configure mock to return common tier
        mock_service = app_with_ebird_filtering._mock_ebird_service
        mock_service._confidence_tiers["Cyanocitta cristata"] = "common"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
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

    async def test_filtering_disabled(self, app_with_temp_data):
        """Should allow all detections when filtering is disabled."""
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

    # Using app_with_ebird_filtering instead of app_with_temp_data because we need
    # eBird filtering enabled with mocked eBird service for this integration test
    async def test_unknown_species_behavior(self, app_with_ebird_filtering):
        """Should handle unknown species according to configuration."""
        # Mock service returns None (species not found)
        # Config has unknown_species_behavior = "allow" by default

        async with AsyncClient(
            transport=ASGITransport(app=app_with_ebird_filtering), base_url="http://test"
        ) as client:
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
    async def test_warn_mode_creates_detection(self, app_with_ebird_filtering):
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
