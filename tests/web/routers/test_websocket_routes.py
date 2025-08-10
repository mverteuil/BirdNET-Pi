"""Test suite for websocket router."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.models.config import BirdNETConfig


class TestWebSocketRouter:
    """Test class for WebSocket router endpoints."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Set up test fixtures with proper path mocking."""
        # Get the real app directory for static assets
        real_app_dir = Path(__file__).parent.parent.parent.parent / "src" / "birdnetpi"

        # Create temp directories for dynamic data
        temp_data_dir = tmp_path / "data"
        temp_data_dir.mkdir()
        (temp_data_dir / "database").mkdir()
        (temp_data_dir / "recordings").mkdir()
        (temp_data_dir / "models").mkdir()
        (temp_data_dir / "config").mkdir()

        # Create the database file to prevent errors
        (temp_data_dir / "database" / "birdnetpi.db").touch()

        # Set environment variables BEFORE importing anything that uses FilePathResolver
        # This ensures FilePathResolver uses temp paths
        self.original_app_env = os.environ.get("BIRDNETPI_APP")
        self.original_data_env = os.environ.get("BIRDNETPI_DATA")
        os.environ["BIRDNETPI_APP"] = str(real_app_dir)
        os.environ["BIRDNETPI_DATA"] = str(temp_data_dir)

        # Now import and create the app with environment-based paths
        from birdnetpi.web.core.factory import create_app

        self.app = create_app()

        # Add mock config object
        self.app.state.config = BirdNETConfig(site_name="Test BirdNET-Pi")

        # Mock WebSocket services
        self.app.state.active_websockets = set()
        self.app.state.audio_websocket_service = Mock()
        self.app.state.audio_websocket_service.connect_websocket = AsyncMock()
        self.app.state.audio_websocket_service.disconnect_websocket = AsyncMock()
        self.app.state.spectrogram_service = Mock()
        self.app.state.spectrogram_service.connect_websocket = AsyncMock()
        self.app.state.spectrogram_service.disconnect_websocket = AsyncMock()

        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up after each test."""
        # Restore original environment variables
        if hasattr(self, "original_app_env"):
            if self.original_app_env is not None:
                os.environ["BIRDNETPI_APP"] = self.original_app_env
            else:
                os.environ.pop("BIRDNETPI_APP", None)

        if hasattr(self, "original_data_env"):
            if self.original_data_env is not None:
                os.environ["BIRDNETPI_DATA"] = self.original_data_env
            else:
                os.environ.pop("BIRDNETPI_DATA", None)

    def test_websocket_routes_endpoints_exist(self):
        """Test that WebSocket router endpoints are registered."""
        # Check that the router has the expected routes
        from birdnetpi.web.routers.websocket_routes import router

        routes = [getattr(route, "path", "") for route in router.routes]  # type: ignore[attr-defined]
        assert "/notifications" in routes  # Notifications WebSocket endpoint
        # Audio and spectrogram endpoints are now handled by standalone daemons

    def test_websocket_routes_basic_structure(self):
        """Test basic router structure without connections."""
        from birdnetpi.web.routers.websocket_routes import router

        # Router should have WebSocket routes (only notifications now)
        assert len(router.routes) == 1

        # All routes should be WebSocket routes
        for route in router.routes:
            assert hasattr(route, "endpoint")

    def test_websocket_dependencies_mocked(self):
        """Test that app state has required WebSocket dependencies."""
        # These should be mocked in setup
        assert hasattr(self.app.state, "active_websockets")
        assert hasattr(self.app.state, "audio_websocket_service")
        assert hasattr(self.app.state, "spectrogram_service")

        # Check that they are the expected mock objects
        assert self.app.state.active_websockets == set()
        assert self.app.state.audio_websocket_service is not None
        assert self.app.state.spectrogram_service is not None

    def test_websocket_endpoint_functions_exist(self):
        """Test that WebSocket endpoint functions are properly defined."""
        from birdnetpi.web.routers.websocket_routes import websocket_endpoint

        # Check that function exists and is callable
        assert callable(websocket_endpoint)
        # Audio and spectrogram endpoints are now handled by standalone daemons

    def test_websocket_routes_imports(self):
        """Test that router imports work correctly."""
        from birdnetpi.web.routers import websocket_routes

        # Should have router
        assert hasattr(websocket_routes, "router")

        # Should have WebSocket endpoint
        assert hasattr(websocket_routes, "websocket_endpoint")
        # Audio and spectrogram endpoints are now handled by standalone daemons

    def test_websocket_route_configuration(self):
        """Test that WebSocket routes are properly configured."""
        from birdnetpi.web.routers.websocket_routes import router

        # Get all route paths
        route_paths = []
        for route in router.routes:
            route_paths.append(getattr(route, "path", ""))  # type: ignore[attr-defined]

        # Should have one WebSocket route
        assert len(route_paths) == 1
        assert "/notifications" in route_paths
        # Audio and spectrogram routes are now handled by standalone daemons

    def test_websocket_route_types(self):
        """Test that all routes are WebSocket routes."""
        from starlette.routing import WebSocketRoute

        from birdnetpi.web.routers.websocket_routes import router

        # All routes should be WebSocket routes
        for route in router.routes:
            assert isinstance(route, WebSocketRoute)

    def test_websocket_logger_configured(self):
        """Test that WebSocket router has logger configured."""
        from birdnetpi.web.routers import websocket_routes

        assert hasattr(websocket_routes, "logger")
        assert websocket_routes.logger.name == "birdnetpi.web.routers.websocket_routes"

    def test_websocket_route_endpoint_mapping(self):
        """Test that routes map to correct endpoint functions."""
        from birdnetpi.web.routers.websocket_routes import router, websocket_endpoint

        # Create mapping of paths to endpoints
        route_mapping = {}
        for route in router.routes:
            route_mapping[getattr(route, "path", "")] = getattr(route, "endpoint", None)  # type: ignore[attr-defined]

        # Check that paths map to correct endpoints
        assert route_mapping["/notifications"] == websocket_endpoint
        # Audio and spectrogram endpoints are now handled by standalone daemons

    def test_websocket_endpoint_parameters(self):
        """Test that WebSocket endpoints have correct parameters."""
        import inspect

        from birdnetpi.web.routers.websocket_routes import websocket_endpoint

        # Endpoint should take websocket parameter
        sig = inspect.signature(websocket_endpoint)
        params = list(sig.parameters.keys())
        assert "websocket" in params
        # Audio and spectrogram endpoints are now handled by standalone daemons

    def test_websocket_routes_fastapi_compatibility(self):
        """Test that WebSocket router is compatible with FastAPI."""
        from fastapi import APIRouter

        from birdnetpi.web.routers.websocket_routes import router

        # Router should be a FastAPI APIRouter
        assert isinstance(router, APIRouter)

    @pytest.mark.skip(reason="WebSocket disconnect testing requires more complex setup")
    def test_websocket_disconnect_cleanup(self):
        """Test that WebSocket disconnection properly cleans up resources."""
        # This test would require more complex WebSocket testing setup
        # to properly test disconnect behavior
        pass
