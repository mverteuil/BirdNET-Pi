"""Test suite for websocket router."""

from unittest.mock import Mock

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
        app.state.spectrogram_service = Mock()

        self.client = TestClient(app)

    def test_websocket_router_endpoints_exist(self):
        """Test that WebSocket router endpoints are registered."""
        # Check that the router has the expected routes
        from birdnetpi.web.routers.websocket_router import router

        routes = [route.path for route in router.routes]
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

    @pytest.mark.skip(reason="WebSocket disconnect testing requires more complex setup")
    def test_websocket_disconnect_cleanup(self):
        """Test that WebSocket disconnection properly cleans up resources."""
        # This test would require more complex WebSocket testing setup
        # to properly test disconnect behavior
        pass
