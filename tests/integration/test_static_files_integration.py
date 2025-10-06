"""Integration tests for static files and templates that reference them."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestStaticFilesIntegration:
    """Static files are properly served and templates can reference them."""

    def test_static_route_exists(self, app_with_temp_data: FastAPI):
        """Should properly mount static route for serving files."""
        # Rather than checking route internals, test that static files are actually served
        with TestClient(app_with_temp_data) as client:
            response = client.get("/static/css/style.css")
            # If we get a 200, the static route exists and works
            assert response.status_code == 200, "Static route not properly mounted"

    def test_static_css_file_is_served(self, app_with_temp_data: FastAPI):
        """Should serve style.css file via static route."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/static/css/style.css")

            assert response.status_code == 200
            assert "text/css" in response.headers.get("content-type", "")

            # Check for some expected CSS content
            assert ":root" in response.text  # CSS variables
            assert "--color-bg-primary" in response.text
            assert "body" in response.text

    def test_index_page_references_static_css(self, app_with_temp_data: FastAPI):
        """Should correctly reference static CSS file in index page."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/css/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text

    def test_settings_page_references_static_css(self, app_with_temp_data: FastAPI):
        """Should correctly reference static CSS file in settings page."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/settings")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/css/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text
            assert "Settings" in response.text or "Configuration" in response.text

    def test_livestream_page_references_static_css(self, app_with_temp_data: FastAPI):
        """Should correctly reference static CSS file in livestream page."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/livestream")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check that the page references the CSS file
            assert "/static/css/style.css" in response.text
            assert '<link rel="stylesheet"' in response.text
            assert "Live" in response.text or "Stream" in response.text

    def test_static_file_not_found(self, app_with_temp_data: FastAPI):
        """Should requesting a non-existent static file returns 404."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/static/nonexistent.css")

            assert response.status_code == 404

    def test_multiple_static_requests(self, app_with_temp_data: FastAPI):
        """Should multiple static file requests work correctly."""
        with TestClient(app_with_temp_data) as client:
            # Make multiple requests for the same static file
            response1 = client.get("/static/css/style.css")
            response2 = client.get("/static/css/style.css")

            assert response1.status_code == 200
            assert response2.status_code == 200

            # Content should be identical
            assert response1.text == response2.text

    def test_css_variables_are_defined(self, app_with_temp_data: FastAPI):
        """Should CSS variables are properly defined in the stylesheet."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/static/css/style.css")

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

    def test_page_styles_are_included(self, app_with_temp_data: FastAPI):
        """Should page-specific styles are included in the stylesheet."""
        with TestClient(app_with_temp_data) as client:
            response = client.get("/static/css/style.css")

            assert response.status_code == 200

            # Check for page-specific styles
            assert ".hero-viz" in response.text  # Index page styles
            assert ".settings-section" in response.text  # Settings page styles
            assert ".status-line" in response.text  # Livestream page styles
            assert ".control-button" in response.text  # Livestream controls
