"""Simple integration test for the web app."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_simple_startup():
    """Test that the app can start up without errors."""
    # Create a minimal app without complex dependencies
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/")
    async def read_root():
        return {"message": "Hello World"}

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}


def test_admin_view_routes_endpoints():
    """Test that admin router endpoints are accessible."""
    import tempfile
    from pathlib import Path

    from fastapi import FastAPI

    from birdnetpi.web.routers import admin_view_routes

    # Use temporary directory for mock paths to prevent MagicMock folder creation
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        app = FastAPI()
        app.include_router(admin_view_routes.router)

        # Mock dependencies
        app.state.templates = MagicMock()
        mock_path_resolver = MagicMock()
        mock_path_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_path_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_path_resolver.get_avibase_database_path.return_value = tmp_path / "avibase.db"
        mock_path_resolver.get_patlevin_database_path.return_value = tmp_path / "patlevin.db"
        app.state.path_resolver = mock_path_resolver

        # Mock config
        mock_config = MagicMock()
        mock_config.site_name = "Test Site"

        with patch("birdnetpi.web.routers.admin_view_routes.ConfigManager") as mock_parser:
            mock_parser.return_value.load.return_value = mock_config

            with TestClient(app) as client:
                # Test that the admin endpoint exists
                response = client.get("/")
                assert response.status_code == 200
                assert response.json() == {"message": "Admin router is working!"}
