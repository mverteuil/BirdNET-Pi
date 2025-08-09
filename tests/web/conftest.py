"""Common fixtures for web application tests."""

import os
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def app_with_temp_data(file_path_resolver) -> Any:
    """Create FastAPI app with properly isolated paths.

    This fixture uses the file_path_resolver fixture from tests/conftest.py
    which properly separates read-only assets (models, IOC db) from writable
    data (database, config, logs) to prevent test pollution.

    IMPORTANT: We must override the Container providers BEFORE creating the app
    because sqladmin_view_routes.setup_sqladmin() calls container.bnp_database_service()
    during app creation, which would instantiate DatabaseService with the default
    /var/lib/birdnetpi path and cause a PermissionError.
    """
    from dependency_injector import providers
    from birdnetpi.web.core.container import Container
    from birdnetpi.services.database_service import DatabaseService
    from birdnetpi.models.config import BirdNETConfig
    from birdnetpi.utils.config_file_parser import ConfigFileParser

    # Override the Container's providers at the class level BEFORE app creation
    # This ensures that when sqladmin calls container.bnp_database_service(),
    # it gets our test version with the temp path
    Container.file_resolver.override(providers.Singleton(lambda: file_path_resolver))
    Container.database_path.override(
        providers.Factory(lambda: file_path_resolver.get_database_path())
    )

    # Create a test config using our file_path_resolver
    parser = ConfigFileParser(file_path_resolver.get_birdnetpi_config_path())
    test_config = parser.load_config()
    Container.config.override(providers.Singleton(lambda: test_config))

    # Create a test database service with the temp path
    temp_db_service = DatabaseService(file_path_resolver.get_database_path())
    Container.bnp_database_service.override(providers.Singleton(lambda: temp_db_service))

    # Now create the app with our overridden providers
    from birdnetpi.web.core.factory import create_app

    app = create_app()

    # Store a reference to the temp_db_service to prevent garbage collection
    app._test_db_service = temp_db_service  # type: ignore[attr-defined]

    # Clean up overrides after the test
    import weakref

    def cleanup():
        Container.file_resolver.reset_override()
        Container.database_path.reset_override()
        Container.config.reset_override()
        Container.bnp_database_service.reset_override()

    # Register cleanup to happen when app is garbage collected
    weakref.finalize(app, cleanup)

    return app
