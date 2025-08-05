"""Tests for field view routes."""

from unittest.mock import MagicMock

import pytest
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.web.core.factory import create_app


@pytest.fixture
def app_with_field_view_routes(file_path_resolver):
    """Create FastAPI app with field view router and dependencies."""
    app = create_app()
    
    if hasattr(app, 'container'):
        # Mock templates
        mock_templates = MagicMock(spec=Jinja2Templates)
        app.container.templates.override(mock_templates)
        
        # Override file resolver
        app.container.file_resolver.override(file_path_resolver)
    
    return app


@pytest.fixture
def client(app_with_field_view_routes):
    """Create test client with field view routes."""
    return TestClient(app_with_field_view_routes)


class TestFieldViewRoutes:
    """Test class for field view endpoints."""

    def test_get_field_mode(self, client):
        """Test field mode page rendering."""
        # Mock the template response with a proper HTMLResponse
        mock_templates = client.app.container.templates()
        mock_html_response = HTMLResponse("<html><body>Field Mode</body></html>")
        mock_templates.TemplateResponse.return_value = mock_html_response

        response = client.get("/field")

        # Should return successful response
        assert response.status_code == 200
        assert "Field Mode" in response.text
        
        # Verify template was called with correct parameters
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args

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
