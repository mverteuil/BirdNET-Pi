"""Fixtures for web router tests."""

import pytest

from birdnetpi.web.core.container import Container


@pytest.fixture
def cache(app_with_temp_data):
    """Provide the mock cache service for router tests.

    This fixture provides direct access to the mock cache that's configured
    in app_with_temp_data. Router tests should use this fixture
    to configure cache behavior for specific test scenarios.

    The app_with_temp_data fixture ensures the Container's cache_service
    is overridden with a MagicMock before the app is created.
    """
    # The Container uses class-level overrides, so we can access it directly
    # The app_with_temp_data fixture ensures the cache is already mocked
    return Container.cache_service()
