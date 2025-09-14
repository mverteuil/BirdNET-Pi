"""Integration test that verifies the FastAPI app starts with real Container."""

import shutil
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


class TestAppStartupIntegration:
    """Test that the FastAPI app starts correctly with real Container."""

    @pytest.fixture
    def test_paths(self, tmp_path: Path, repo_root: Path):
        """Should create test directory structure with real assets copied."""
        # Create directory structure
        (tmp_path / "database").mkdir(parents=True)
        (tmp_path / "config").mkdir(parents=True)

        # Copy real databases to temp location
        for db_name in ["ioc_reference.db", "avibase_database.db", "patlevin_database.db"]:
            real_db = repo_root / "data" / "database" / db_name
            if real_db.exists():
                temp_db = tmp_path / "database" / db_name
                shutil.copy(real_db, temp_db)

        # Copy config template
        real_config = repo_root / "config_templates" / "birdnetpi.yaml"
        if real_config.exists():
            temp_config = tmp_path / "config" / "birdnetpi.yaml"
            shutil.copy(real_config, temp_config)

        return tmp_path

    @pytest.fixture
    def test_resolver(self, test_paths: Path, repo_root: Path):
        """Should create a PathResolver configured for testing."""
        resolver = PathResolver()

        # Override writable paths to use temp directory
        resolver.get_database_path = lambda: test_paths / "database" / "birdnetpi.db"
        resolver.get_birdnetpi_config_path = lambda: test_paths / "config" / "birdnetpi.yaml"

        # Override read-only database paths to use temp copies
        resolver.get_ioc_database_path = lambda: test_paths / "database" / "ioc_reference.db"
        resolver.get_avibase_database_path = lambda: test_paths / "database" / "avibase_database.db"
        resolver.get_patlevin_database_path = (
            lambda: test_paths / "database" / "patlevin_database.db"
        )

        # Keep real paths for models, static files, templates
        resolver.get_models_dir = lambda: repo_root / "data" / "models"
        resolver.get_static_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "static"
        resolver.get_templates_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "templates"
        resolver.get_config_template_path = (
            lambda: repo_root / "config_templates" / "birdnetpi.yaml"
        )

        return resolver

    @pytest.fixture
    def app_with_real_container(self, test_resolver: PathResolver):
        """Create the app with a real Container using test paths."""
        # Override Container providers before creating app
        Container.path_resolver.override(providers.Singleton(lambda: test_resolver))
        Container.database_path.override(
            providers.Factory(lambda: test_resolver.get_database_path())
        )

        # Create the app using the factory
        app = create_app()

        yield app

        # Clean up overrides
        Container.path_resolver.reset_override()
        Container.database_path.reset_override()

    def test_app_creation_succeeds(self, app_with_real_container: FastAPI):
        """Should the app can be created without errors."""
        assert app_with_real_container is not None
        assert isinstance(app_with_real_container, FastAPI)
        assert hasattr(app_with_real_container, "container")

    def test_app_container_is_wired(self, app_with_real_container: FastAPI):
        """Should the app's container is properly wired."""
        container = app_with_real_container.container  # type: ignore[attr-defined]
        assert container is not None
        # Check that it has the expected Container attributes rather than exact type
        assert hasattr(container, "config")
        assert hasattr(container, "path_resolver")
        assert hasattr(container, "core_database")

    def test_app_has_routes(self, app_with_real_container: FastAPI):
        """Should the app has routes registered."""
        routes = [route.path for route in app_with_real_container.routes]  # type: ignore[attr-defined]

        # Check for expected routes
        assert "/" in routes
        assert "/api/system/hardware/status" in routes
        assert "/api/detections/recent" in routes
        # assert "/reports/today" in routes  # Removed from codebase
        assert "/admin/settings" in routes

    def test_root_endpoint_works(self, app_with_real_container: FastAPI):
        """Should the root endpoint returns a successful response."""
        with TestClient(app_with_real_container) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "html" in response.text.lower()

    def test_api_endpoint_works(self, app_with_real_container: FastAPI):
        """Should an API endpoint works with the real container."""
        with TestClient(app_with_real_container) as client:
            response = client.get("/api/system/hardware/status")
            assert response.status_code == 200
            data = response.json()
            assert "components" in data
            assert "cpu" in data["components"]

    def test_container_providers_are_instantiable(self, app_with_real_container: FastAPI):
        """Should container providers can be instantiated."""
        container = app_with_real_container.container  # type: ignore[attr-defined]

        # Test critical providers
        config = container.config()
        assert config is not None

        path_resolver = container.path_resolver()
        assert path_resolver is not None

        db_service = container.core_database()
        assert db_service is not None

    def test_multiple_requests_work(self, app_with_real_container: FastAPI):
        """Should multiple requests work correctly (singleton behavior)."""
        with TestClient(app_with_real_container) as client:
            # Make multiple requests
            response1 = client.get("/")
            response2 = client.get("/api/system/hardware/status")
            response3 = client.get("/")

            assert response1.status_code == 200
            assert response2.status_code == 200
            assert response3.status_code == 200

    def test_websocket_endpoints_exist(self, app_with_real_container: FastAPI):
        """Should WebSocket endpoints are registered."""
        # Check for WebSocket routes
        assert "/ws/notifications" in [route.path for route in app_with_real_container.routes]  # type: ignore[attr-defined]

    def test_admin_sqladmin_is_setup(self, app_with_real_container: FastAPI):
        """Should SQLAdmin is properly set up."""
        # Check that admin routes are registered
        admin_routes = [
            route.path  # type: ignore[attr-defined]
            for route in app_with_real_container.routes
            if route.path.startswith("/admin")  # type: ignore[attr-defined]
        ]
        assert len(admin_routes) > 0

    def test_middleware_is_configured(self, app_with_real_container: FastAPI):
        """Should middleware is properly configured."""
        # Check that the app has the translation manager in state (set by LanguageMiddleware)
        assert hasattr(app_with_real_container.state, "translation_manager")
        assert app_with_real_container.state.translation_manager is not None

    def test_translation_manager_is_available(self, app_with_real_container: FastAPI):
        """Should translation manager is set up in app state."""
        assert hasattr(app_with_real_container.state, "translation_manager")
        assert app_with_real_container.state.translation_manager is not None
