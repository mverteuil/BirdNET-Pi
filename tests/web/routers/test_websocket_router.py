"""Test suite for websocket router."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.web.main import app


class TestWebSocketRouter:
    """Test class for WebSocket router endpoints."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
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

    def test_websocket_router_endpoints_exist(self):
        """Test that WebSocket router endpoints are registered."""
        # Check that the router has the expected routes
        from birdnetpi.web.routers.websocket_router import router

        routes = [getattr(route, 'path', '') for route in router.routes]  # type: ignore[attr-defined]
        assert "" in routes  # Base WebSocket endpoint
        assert "/audio" in routes  # Audio WebSocket endpoint
        assert "/spectrogram" in routes  # Spectrogram WebSocket endpoint

    def test_websocket_router_basic_structure(self):
        """Test basic router structure without connections."""
        from birdnetpi.web.routers.websocket_router import router

        # Router should have WebSocket routes
        assert len(router.routes) == 3

        # All routes should be WebSocket routes
        for route in router.routes:
            assert hasattr(route, "endpoint")

    def test_websocket_dependencies_mocked(self):
        """Test that app state has required WebSocket dependencies."""
        # These should be mocked in setup
        assert hasattr(app.state, "active_websockets")
        assert hasattr(app.state, "audio_websocket_service")
        assert hasattr(app.state, "spectrogram_service")

        # Check that they are the expected mock objects
        assert app.state.active_websockets == set()
        assert app.state.audio_websocket_service is not None
        assert app.state.spectrogram_service is not None

    def test_websocket_endpoint_functions_exist(self):
        """Test that WebSocket endpoint functions are properly defined."""
        from birdnetpi.web.routers.websocket_router import (
            websocket_endpoint,
            audio_websocket_endpoint,
            spectrogram_websocket_endpoint
        )
        
        # Check that functions exist and are callable
        assert callable(websocket_endpoint)
        assert callable(audio_websocket_endpoint)
        assert callable(spectrogram_websocket_endpoint)

    def test_websocket_router_imports(self):
        """Test that router imports work correctly."""
        from birdnetpi.web.routers import websocket_router
        
        # Should have router
        assert hasattr(websocket_router, 'router')
        
        # Should have WebSocket endpoints
        assert hasattr(websocket_router, 'websocket_endpoint')
        assert hasattr(websocket_router, 'audio_websocket_endpoint')
        assert hasattr(websocket_router, 'spectrogram_websocket_endpoint')

    def test_websocket_route_configuration(self):
        """Test that WebSocket routes are properly configured."""
        from birdnetpi.web.routers.websocket_router import router
        
        # Get all route paths
        route_paths = []
        for route in router.routes:
            route_paths.append(getattr(route, 'path', ''))  # type: ignore[attr-defined]
        
        # Should have three WebSocket routes
        assert len(route_paths) == 3
        assert "" in route_paths
        assert "/audio" in route_paths
        assert "/spectrogram" in route_paths

    def test_websocket_route_types(self):
        """Test that all routes are WebSocket routes."""
        from birdnetpi.web.routers.websocket_router import router
        from starlette.routing import WebSocketRoute
        
        # All routes should be WebSocket routes
        for route in router.routes:
            assert isinstance(route, WebSocketRoute)

    def test_websocket_logger_configured(self):
        """Test that WebSocket router has logger configured."""
        from birdnetpi.web.routers import websocket_router
        
        assert hasattr(websocket_router, 'logger')
        assert websocket_router.logger.name == 'birdnetpi.web.routers.websocket_router'

    def test_websocket_route_endpoint_mapping(self):
        """Test that routes map to correct endpoint functions."""
        from birdnetpi.web.routers.websocket_router import (
            router,
            websocket_endpoint,
            audio_websocket_endpoint, 
            spectrogram_websocket_endpoint
        )
        
        # Create mapping of paths to endpoints
        route_mapping = {}
        for route in router.routes:
            route_mapping[getattr(route, 'path', '')] = getattr(route, 'endpoint', None)  # type: ignore[attr-defined]
        
        # Check that paths map to correct endpoints
        assert route_mapping[""] == websocket_endpoint
        assert route_mapping["/audio"] == audio_websocket_endpoint
        assert route_mapping["/spectrogram"] == spectrogram_websocket_endpoint

    def test_websocket_endpoint_parameters(self):
        """Test that WebSocket endpoints have correct parameters."""
        import inspect
        from birdnetpi.web.routers.websocket_router import (
            websocket_endpoint,
            audio_websocket_endpoint,
            spectrogram_websocket_endpoint
        )
        
        # All endpoints should take websocket and request parameters
        for endpoint in [websocket_endpoint, audio_websocket_endpoint, spectrogram_websocket_endpoint]:
            sig = inspect.signature(endpoint)
            params = list(sig.parameters.keys())
            assert "websocket" in params
            assert "request" in params

    def test_websocket_router_fastapi_compatibility(self):
        """Test that WebSocket router is compatible with FastAPI."""
        from birdnetpi.web.routers.websocket_router import router
        from fastapi import APIRouter
        
        # Router should be a FastAPI APIRouter
        assert isinstance(router, APIRouter)

    @pytest.mark.skip(reason="WebSocket disconnect testing requires more complex setup")
    def test_websocket_disconnect_cleanup(self):
        """Test that WebSocket disconnection properly cleans up resources."""
        # This test would require more complex WebSocket testing setup
        # to properly test disconnect behavior
        pass
