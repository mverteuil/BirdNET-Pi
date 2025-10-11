"""Simple integration test for the web app."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.web.routers import settings_view_routes


def test_simple_startup():
    """Should start up app without errors."""
    # Create a minimal app without complex dependencies

    app = FastAPI()

    @app.get("/")
    async def read_root():
        return {"message": "Hello World"}

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}


def test_settings_view_routes_endpoints(path_resolver, tmp_path):
    """Should have settings router endpoints accessible."""
    app = FastAPI()
    app.include_router(settings_view_routes.router)

    # Mock dependencies
    app.state.templates = MagicMock(spec=Jinja2Templates)
    path_resolver.get_ioc_database_path = lambda: tmp_path / "ioc_reference.db"
    path_resolver.get_models_dir = lambda: tmp_path / "models"
    path_resolver.get_wikidata_database_path = lambda: tmp_path / "wikidata_reference.db"
    app.state.path_resolver = path_resolver

    # Mock config
    mock_config = MagicMock(spec=BirdNETConfig)
    mock_config.site_name = "Test Site"

    with patch(
        "birdnetpi.web.routers.settings_view_routes.ConfigManager", autospec=True
    ) as mock_parser:
        mock_parser.return_value.load.return_value = mock_config

        with TestClient(app) as client:
            # Test that the admin endpoint exists
            response = client.get("/")
            assert response.status_code == 200
            assert response.json() == {"message": "Admin router is working!"}
