"""Integration tests for admin router that exercise expanded functionality."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.web.core.factory import create_app


@pytest.fixture(scope="function")
def app_with_admin_view_routes(tmp_path):
    """Create FastAPI app with admin router and dependencies using the factory."""
    # Create test config file for settings endpoint
    config_file = tmp_path / "config.yaml"
    config_file.write_text("site_name: Test BirdNET-Pi\nlatitude: 40.7128\nlongitude: -74.0060")

    # Mock the database service completely to avoid SQLite issues
    mock_db_instance = Mock()
    mock_db_instance.get_db.return_value.__enter__ = Mock()
    mock_db_instance.get_db.return_value.__exit__ = Mock()

    # Mock file resolver to use test config and temp database path
    mock_resolver = Mock()
    mock_resolver.get_birdnetpi_config_path.return_value = str(config_file)
    mock_resolver.base_dir = str(tmp_path)
    mock_resolver.get_database_path.return_value = str(tmp_path / f"test_db_{id(tmp_path)}.sqlite")

    # Mock detection manager for test_detection endpoint
    mock_detection_manager = MagicMock(spec=DetectionManager)
    mock_detection_manager.create_detection.return_value = None

    # Create the app using the factory
    app = create_app()

    # Override dependencies to use mocks
    if hasattr(app, "container"):
        app.container.file_resolver.override(mock_resolver)  # type: ignore[attr-defined]
        app.container.detection_manager.override(mock_detection_manager)  # type: ignore[attr-defined]
        app.container.bnp_database_service.override(mock_db_instance)  # type: ignore[attr-defined]

    yield app

    # Clean up: reset overrides after each test
    if hasattr(app, "container"):
        app.container.file_resolver.reset_override()  # type: ignore[attr-defined]
        app.container.detection_manager.reset_override()  # type: ignore[attr-defined]
        app.container.bnp_database_service.reset_override()  # type: ignore[attr-defined]


@pytest.fixture
def client(app_with_admin_view_routes):
    """Create test client with real app."""
    return TestClient(app_with_admin_view_routes)


class TestAdminRouterIntegration:
    """Integration tests for admin router with basic functionality."""

    def test_admin_endpoint_returns_json(self, client):
        """Should return JSON response with admin message."""
        response = client.get("/admin/")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert isinstance(data, dict)
        assert "message" in data
        assert data["message"] == "Admin router is working!"

    def test_admin_endpoint_returns_correct_structure(self, client):
        """Should return expected JSON structure."""
        response = client.get("/admin")

        assert response.status_code == 200
        data = response.json()

        # Should be a dictionary with exactly one key-value pair
        assert len(data) == 1
        assert list(data.keys()) == ["message"]
        assert isinstance(data["message"], str)

    def test_admin_endpoint_is_accessible(self, client):
        """Should be accessible without authentication or parameters."""
        response = client.get("/admin")

        # Should not require any authentication or special headers
        assert response.status_code == 200
        assert response.status_code != 401  # Not unauthorized
        assert response.status_code != 403  # Not forbidden

    def test_admin_endpoint_handles_multiple_requests(self, client):
        """Should handle multiple consecutive requests consistently."""
        for _ in range(3):
            response = client.get("/admin")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Admin router is working!"

    def test_admin_endpoint_only_supports_get_method(self, client):
        """Should only support GET method."""
        # Test that other HTTP methods are not allowed
        unsupported_methods = [
            ("post", client.post),
            ("put", client.put),
            ("delete", client.delete),
            ("patch", client.patch),
            ("head", client.head),
            ("options", client.options),
        ]

        for _, method_func in unsupported_methods:
            response = method_func("/admin")
            # Should return 405 Method Not Allowed or 404 Not Found
            assert response.status_code in [404, 405]

    def test_admin_endpoint_content_encoding(self, client):
        """Should return properly encoded content."""
        response = client.get("/admin")

        assert response.status_code == 200
        # Should be valid JSON that can be decoded
        data = response.json()
        assert isinstance(data, dict)

        # Check that the response text is also valid
        assert "Admin router is working!" in response.text

    def test_admin_endpoint_response_headers(self, client):
        """Should return appropriate response headers."""
        response = client.get("/admin")

        assert response.status_code == 200
        assert "content-type" in response.headers
        assert response.headers["content-type"] == "application/json"
        assert "content-length" in response.headers

        # Content length should match actual content
        expected_length = len(response.content)
        assert int(response.headers["content-length"]) == expected_length

    def test_admin_endpoint_is_async_function(self, client):
        """Should work correctly as an async endpoint."""
        # This test verifies that the async nature doesn't cause issues
        response = client.get("/admin")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Admin router is working!"

    def test_admin_endpoint_returns_static_content(self, client):
        """Should return the same static content each time."""
        # Make multiple requests and verify consistency
        responses = []
        for _ in range(5):
            response = client.get("/admin")
            responses.append(response.json())

        # All responses should be identical
        first_response = responses[0]
        for response in responses[1:]:
            assert response == first_response
            assert response["message"] == "Admin router is working!"

    def test_admin_endpoint_minimal_functionality(self, client):
        """Should provide minimal but working admin functionality."""
        response = client.get("/admin")

        assert response.status_code == 200
        data = response.json()

        # This is a basic health check endpoint
        assert "message" in data
        assert len(data["message"]) > 0
        assert "working" in data["message"].lower()

    def test_admin_endpoint_no_side_effects(self, client):
        """Should not cause any side effects when called."""
        # Call the endpoint multiple times
        for _ in range(3):
            response = client.get("/admin")
            assert response.status_code == 200

        # Each call should return the same result (no side effects)
        final_response = client.get("/admin")
        assert final_response.status_code == 200
        data = final_response.json()
        assert data["message"] == "Admin router is working!"

    def test_settings_page_renders(self, client):
        """Should render settings page with configuration."""
        response = client.get("/admin/settings")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        # Check that some expected content is in the response
        assert "Test BirdNET-Pi" in response.text

    @patch("birdnetpi.web.routers.admin_view_routes.LogService")
    def test_log_endpoint_returns_logs(self, mock_log_service, client):
        """Should return system logs as plain text."""
        # Mock log service
        mock_service_instance = Mock()
        mock_service_instance.get_logs.return_value = "Test log content\nLine 2\n"
        mock_log_service.return_value = mock_service_instance

        response = client.get("/admin/log")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "Test log content" in response.text

    def test_test_detection_form_renders(self, client):
        """Should render test detection form template."""
        response = client.get("/admin/test_detection_form")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_test_detection_endpoint_creates_detection(self, client):
        """Should create a test detection event."""
        response = client.get("/admin/test_detection?species=Test Bird&confidence=0.95")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Test detection published" in data["message"]
        assert "data" in data

    def test_test_detection_endpoint_with_defaults(self, client):
        """Should use default values when parameters are not provided."""
        response = client.get("/admin/test_detection")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Test detection published"
        # Should have used default species "Test Bird"
        assert "Test Bird" in data["data"]
