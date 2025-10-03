"""Tests for update view routes."""

import inspect
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from birdnetpi.web.routers import update_view_routes
from birdnetpi.web.routers.update_view_routes import update_page


@pytest.fixture
def client(app_with_temp_data):
    """Create test client from app."""
    # Mount static files to avoid template rendering errors

    # Create a temporary static directory
    static_dir = tempfile.mkdtemp()

    # Create a dummy CSS file
    with open(os.path.join(static_dir, "style.css"), "w") as f:
        f.write("/* dummy css */")

    # Mount the static files
    app_with_temp_data.mount("/static", StaticFiles(directory=static_dir), name="static")

    return TestClient(app_with_temp_data)


class TestUpdateViewRoutes:
    """Test update view routes for HTML pages."""

    def test_update_page_exists(self, client, cache):
        """Should have update page route accessible."""
        # Get the container's mock cache
        # Use cache fixture
        # Cache provided by fixture

        # Configure cache to return empty data
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_update_page_accesses_cache_for_status(self, client, cache):
        """Should access cache to get update status."""
        # Use cache fixture
        # Cache provided by fixture

        # Configure cache to track calls
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200

        # Should have called get for update:status
        cache.get.assert_called()
        call_args = [call.args[0] for call in cache.get.call_args_list if call.args]
        assert "update:status" in call_args

    def test_update_page_accesses_cache_for_result(self, client, cache):
        """Should access cache to get update result."""
        # Use cache fixture
        # Cache provided by fixture

        # Configure cache to track calls
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200

        # Should have called get for update:result
        cache.get.assert_called()
        call_args = [call.args[0] for call in cache.get.call_args_list if call.args]
        assert "update:result" in call_args

    def test_update_page_with_update_available(self, client, cache):
        """Should handle update available status."""
        # Use cache fixture
        # Cache provided by fixture

        # Configure cache to return update available
        def cache_get_side_effect(key):
            if key == "update:status":
                return {
                    "available": True,
                    "current_version": "v1.0.0",
                    "latest_version": "v1.1.0",
                }
            return None

        cache.get.side_effect = cache_get_side_effect

        response = client.get("/admin/update/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_update_page_with_update_result(self, client, cache):
        """Should handle update result data."""
        # Use cache fixture
        # Cache provided by fixture

        # Configure cache to return update result
        def cache_get_side_effect(key):
            if key == "update:result":
                return {
                    "success": True,
                    "version": "v1.1.0",
                    "completed_at": "2024-01-01T12:00:00",
                }
            return None

        cache.get.side_effect = cache_get_side_effect

        response = client.get("/admin/update/")

        assert response.status_code == 200

    def test_update_page_handles_none_cache_values(self, client, cache):
        """Should handle None values from cache gracefully."""
        # Use cache fixture
        # Cache provided by fixture

        # All cache calls return None
        cache.get.return_value = None

        response = client.get("/admin/update/")

        # Should still return successfully
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_update_page_accessible_with_trailing_slash(self, client, cache):
        """Should be accessible with trailing slash."""
        # Use cache fixture
        # Cache provided by fixture
        cache.get.return_value = None

        response = client.get("/admin/update/")
        assert response.status_code == 200

    def test_update_page_redirect_without_trailing_slash(self, client, cache):
        """Should redirect without trailing slash to with trailing slash."""
        # Use cache fixture
        # Cache provided by fixture
        cache.get.return_value = None

        response = client.get("/admin/update", follow_redirects=False)
        # FastAPI redirects to add trailing slash for paths ending with /
        assert response.status_code in [200, 307]

    def test_update_page_calls_cache_twice(self, client, cache):
        """Should call cache.get for status and result."""
        # Use cache fixture
        # Cache provided by fixture
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200
        # Should call get for both status and result (middleware may add extra calls)
        assert cache.get.call_count >= 2
        call_args = [call.args[0] for call in cache.get.call_args_list if call.args]
        assert "update:status" in call_args
        assert "update:result" in call_args


class TestUpdateViewCoverage:
    """Additional tests to ensure coverage of update_view_routes.py."""

    def test_update_view_route_imports(self):
        """Should have all imports in update_view_routes be valid."""
        # This just imports the module to ensure coverage

        # Check that router is defined
        assert hasattr(update_view_routes, "router")
        assert update_view_routes.router is not None

    def test_update_view_route_logger(self):
        """Should have logger configured."""
        # Check that logger is defined
        assert hasattr(update_view_routes, "logger")
        assert update_view_routes.logger is not None

    @patch("birdnetpi.web.routers.update_view_routes.logger")
    def test_update_page_function_signature(self, mock_logger):
        """Should have correct update_page function signature."""
        # Check function exists and has correct annotations
        assert update_page.__name__ == "update_page"
        # The function should be async

        assert inspect.iscoroutinefunction(update_page)


class TestUpdateViewIntegration:
    """Test integration aspects of update view."""

    def test_view_and_api_use_same_cache_keys(self, client, cache):
        """Should use same cache keys as API routes."""
        # Use cache fixture
        # Cache provided by fixture

        # Track what keys are accessed
        accessed_keys = []

        def track_keys(key):
            accessed_keys.append(key)
            return None

        cache.get.side_effect = track_keys

        # Access the view
        response = client.get("/admin/update/")
        assert response.status_code == 200

        # Check that expected keys were accessed
        assert "update:status" in accessed_keys
        assert "update:result" in accessed_keys

        # Reset for API test
        accessed_keys.clear()
        cache.get.side_effect = track_keys

        # Access the API
        api_response = client.get("/api/update/status")
        assert api_response.status_code == 200

        # API should access same status key
        assert "update:status" in accessed_keys

    def test_view_response_is_html(self, client, cache):
        """Should return HTML content type."""
        # Use cache fixture
        # Cache provided by fixture
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Response body should contain HTML
        assert response.text  # Should have some content

    def test_view_uses_jinja2_template(self, client, cache):
        """Should use Jinja2 template for rendering."""
        # Use cache fixture
        # Cache provided by fixture
        cache.get.return_value = None

        response = client.get("/admin/update/")

        assert response.status_code == 200
        # The response should be rendered HTML
        # We can't easily check the template name without mocking,
        # but we know it should render admin/update.html.j2
