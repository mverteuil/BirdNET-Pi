"""Test suite for websocket router."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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
        
        # Mock FilePathResolver to use temp dirs for dynamic data but real dirs for static assets
        with patch('birdnetpi.utils.file_path_resolver.FilePathResolver') as mock_resolver_class:
            mock_resolver = Mock()
            # Static assets from real directories
            mock_resolver.app_dir = real_app_dir
            mock_resolver.base_dir = str(real_app_dir)
            mock_resolver.get_config_template_path.return_value = str(real_app_dir / "config_templates" / "birdnetpi.yaml")
            mock_resolver.get_ioc_database_path.return_value = str(real_app_dir / "data" / "database" / "ioc_reference.db")
            # Dynamic data to temp directories
            mock_resolver.data_dir = temp_data_dir
            mock_resolver.get_database_path.return_value = str(temp_data_dir / "database" / "birdnetpi.db")
            mock_resolver.get_recordings_dir.return_value = str(temp_data_dir / "recordings")
            mock_resolver.get_models_dir.return_value = str(temp_data_dir / "models")
            mock_resolver.get_birdnetpi_config_path.return_value = str(real_app_dir / "config_templates" / "birdnetpi.yaml")
            mock_resolver_class.return_value = mock_resolver
            
            # Now import the app with mocked paths
            from birdnetpi.web.main import app
            self.app = app

        # Add mock config object
        app.state.config = BirdNETConfig(site_name="Test BirdNET-Pi")

        # Mock WebSocket services
        app.state.active_websockets = set()
        app.state.audio_websocket_service = Mock()
        app.state.audio_websocket_service.connect_websocket = AsyncMock()
        app.state.audio_websocket_service.disconnect_websocket = AsyncMock()
        app.state.spectrogram_service = Mock()
        app.state.spectrogram_service.connect_websocket = AsyncMock()
        app.state.spectrogram_service.disconnect_websocket = AsyncMock()

        self.client = TestClient(app)

    def test_websocket_routes_endpoints_exist(self):
        """Test that WebSocket router endpoints are registered."""
        # Check that the router has the expected routes
        from birdnetpi.web.routers.websocket_routes import router

        routes = [getattr(route, "path", "") for route in router.routes]  # type: ignore[attr-defined]
        assert "/notifications" in routes  # Notifications WebSocket endpoint
        assert "/audio" in routes  # Audio WebSocket endpoint
        assert "/spectrogram" in routes  # Spectrogram WebSocket endpoint

    def test_websocket_routes_basic_structure(self):
        """Test basic router structure without connections."""
        from birdnetpi.web.routers.websocket_routes import router

        # Router should have WebSocket routes
        assert len(router.routes) == 3

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
        from birdnetpi.web.routers.websocket_routes import (
            audio_websocket_endpoint,
            spectrogram_websocket_endpoint,
            websocket_endpoint,
        )

        # Check that functions exist and are callable
        assert callable(websocket_endpoint)
        assert callable(audio_websocket_endpoint)
        assert callable(spectrogram_websocket_endpoint)

    def test_websocket_routes_imports(self):
        """Test that router imports work correctly."""
        from birdnetpi.web.routers import websocket_routes

        # Should have router
        assert hasattr(websocket_routes, "router")

        # Should have WebSocket endpoints
        assert hasattr(websocket_routes, "websocket_endpoint")
        assert hasattr(websocket_routes, "audio_websocket_endpoint")
        assert hasattr(websocket_routes, "spectrogram_websocket_endpoint")

    def test_websocket_route_configuration(self):
        """Test that WebSocket routes are properly configured."""
        from birdnetpi.web.routers.websocket_routes import router

        # Get all route paths
        route_paths = []
        for route in router.routes:
            route_paths.append(getattr(route, "path", ""))  # type: ignore[attr-defined]

        # Should have three WebSocket routes
        assert len(route_paths) == 3
        assert "/notifications" in route_paths
        assert "/audio" in route_paths
        assert "/spectrogram" in route_paths

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
        from birdnetpi.web.routers.websocket_routes import (
            audio_websocket_endpoint,
            router,
            spectrogram_websocket_endpoint,
            websocket_endpoint,
        )

        # Create mapping of paths to endpoints
        route_mapping = {}
        for route in router.routes:
            route_mapping[getattr(route, "path", "")] = getattr(route, "endpoint", None)  # type: ignore[attr-defined]

        # Check that paths map to correct endpoints
        assert route_mapping["/notifications"] == websocket_endpoint
        assert route_mapping["/audio"] == audio_websocket_endpoint
        assert route_mapping["/spectrogram"] == spectrogram_websocket_endpoint

    def test_websocket_endpoint_parameters(self):
        """Test that WebSocket endpoints have correct parameters."""
        import inspect

        from birdnetpi.web.routers.websocket_routes import (
            audio_websocket_endpoint,
            spectrogram_websocket_endpoint,
            websocket_endpoint,
        )

        # All endpoints should take websocket and request parameters
        for endpoint in [
            websocket_endpoint,
            audio_websocket_endpoint,
            spectrogram_websocket_endpoint,
        ]:
            sig = inspect.signature(endpoint)
            params = list(sig.parameters.keys())
            assert "websocket" in params
            assert "request" in params

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
