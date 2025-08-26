"""Integration tests for static files and templates that reference them."""

import shutil
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


class TestStaticFilesIntegration:
    """Test that static files are properly served and templates can reference them."""

    @pytest.fixture
    def test_paths(self, tmp_path: Path, repo_root: Path):
        """Create test directory structure with real assets copied."""
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
        """Create a PathResolver configured for testing."""
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
    def app_with_static(self, test_resolver: PathResolver):
        """Create the app with static files properly mounted."""
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

    def test_static_route_exists(self, app_with_static: FastAPI):
        """Test that the static route is properly mounted by testing it works."""
        # Rather than checking route internals, test that static files are actually served
        with TestClient(app_with_static) as client:
            response = client.get("/static/style.css")
            # If we get a 200, the static route exists and works
            assert response.status_code == 200, "Static route not properly mounted"

    def test_static_css_file_is_served(self, app_with_static: FastAPI):
        """Test that the style.css file can be accessed via static route."""
        with TestClient(app_with_static) as client:
            response = client.get("/static/style.css")

            assert response.status_code == 200
            assert "text/css" in response.headers.get("content-type", "")

            # Check for some expected CSS content
            assert ":root" in response.text  # CSS variables
            assert "--color-bg-primary" in response.text
            assert "body" in response.text

    def test_index_page_references_static_css(self, app_with_static: FastAPI):
        """Test that the index page correctly references the static CSS file."""
        with TestClient(app_with_static) as client:
            response = client.get("/")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text

    def test_settings_page_references_static_css(self, app_with_static: FastAPI):
        """Test that the settings page correctly references the static CSS file."""
        with TestClient(app_with_static) as client:
            response = client.get("/admin/settings")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text
            assert "Settings" in response.text or "Configuration" in response.text

    def test_livestream_page_references_static_css(self, app_with_static: FastAPI):
        """Test that the livestream page correctly references the static CSS file."""
        with TestClient(app_with_static) as client:
            response = client.get("/livestream")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text
            assert "Live" in response.text or "Stream" in response.text

    def test_static_file_not_found(self, app_with_static: FastAPI):
        """Test that requesting a non-existent static file returns 404."""
        with TestClient(app_with_static) as client:
            response = client.get("/static/nonexistent.css")

            assert response.status_code == 404

    def test_multiple_static_requests(self, app_with_static: FastAPI):
        """Test that multiple static file requests work correctly."""
        with TestClient(app_with_static) as client:
            # Make multiple requests for the same static file
            response1 = client.get("/static/style.css")
            response2 = client.get("/static/style.css")

            assert response1.status_code == 200
            assert response2.status_code == 200

            # Content should be identical
            assert response1.text == response2.text

    def test_css_variables_are_defined(self, app_with_static: FastAPI):
        """Test that CSS variables are properly defined in the stylesheet."""
        with TestClient(app_with_static) as client:
            response = client.get("/static/style.css")

            assert response.status_code == 200

            # Check for key CSS variables
            css_vars = [
                "--color-bg-primary",
                "--color-text-primary",
                "--color-border-primary",
                "--color-status-success",
                "--color-status-critical",
            ]

            for var in css_vars:
                assert var in response.text, f"CSS variable {var} not found in stylesheet"

    def test_page_styles_are_included(self, app_with_static: FastAPI):
        """Test that page-specific styles are included in the stylesheet."""
        with TestClient(app_with_static) as client:
            response = client.get("/static/style.css")

            assert response.status_code == 200

            # Check for page-specific styles
            assert ".hero-viz" in response.text  # Index page styles
            assert ".settings-section" in response.text  # Settings page styles
            assert ".status-line" in response.text  # Livestream page styles
            assert ".control-button" in response.text  # Livestream controls
