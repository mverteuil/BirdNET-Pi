"""Tests for field view routes."""

from unittest.mock import MagicMock

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates

from birdnetpi.web.routers.field_view_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""

    templates = providers.Singleton(MagicMock, spec=Jinja2Templates)


@pytest.fixture
def app_with_field_view_routes():
    """Create FastAPI app with field view router and dependencies."""
    app = FastAPI()
    
    # Create test container
    container = TestContainer()
    
    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.field_view_routes"])
    app.container = container
    
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_field_view_routes):
    """Create test client with field view routes."""
    return TestClient(app_with_field_view_routes)


class TestFieldViewRoutes:
    """Test class for field view endpoints."""

    def test_get_field_mode(self, client):
        """Test field mode page rendering."""
        # Mock the template response
        mock_response = MagicMock()
        mock_response.status_code = 200
        client.app.container.templates().TemplateResponse.return_value = mock_response
        
        response = client.get("/field")
        
        # Verify template was called with correct parameters
        client.app.container.templates().TemplateResponse.assert_called_once()
        call_args = client.app.container.templates().TemplateResponse.call_args
        
        # Check template name
        assert call_args[0][0] == "field_mode.html"
        
        # Check context contains request
        context = call_args[0][1]
        assert "request" in context

    def test_field_mode_endpoint_exists(self, client):
        """Test that the field mode endpoint is properly registered."""
        # Check that the route exists by examining the app's routes
        routes = [route.path for route in client.app.routes]
        assert "/field" in routes