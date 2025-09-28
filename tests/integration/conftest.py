"""Integration test fixtures.

This conftest.py provides fixtures specifically for integration tests.
It extends/overrides fixtures from the parent conftest.py to provide
more suitable behavior for integration testing.
"""

import pytest

from birdnetpi.web.core.container import Container


@pytest.fixture
def cache(app_with_temp_data):
    """Provide the cache service for integration tests.

    This fixture provides direct access to the mock cache that's configured
    in app_with_temp_data. Integration tests should use this fixture
    to configure cache behavior for specific test scenarios.

    Example:
        def test_cache_failure(client, cache):
            # Configure the cache to fail
            cache.set.side_effect = Exception("Redis connection lost")
            response = client.post("/api/update/check")
            assert response.status_code == 500

        def test_cache_returns_data(client, cache):
            # Configure cache to return specific data
            cache.get.return_value = {"status": "ready"}
            response = client.get("/api/update/status")
            assert response.json()["status"] == "ready"
    """
    # The Container uses class-level overrides, so we can access it directly
    # The app_with_temp_data fixture ensures the cache is already mocked
    return Container.cache_service()
