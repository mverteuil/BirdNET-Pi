"""Integration tests for admin router that exercise basic functionality."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.web.routers.admin_router import router


@pytest.fixture
def app_with_admin_router():
    """Create FastAPI app with admin router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_admin_router):
    """Create test client with real app."""
    return TestClient(app_with_admin_router)


class TestAdminRouterIntegration:
    """Integration tests for admin router with basic functionality."""

    def test_admin_endpoint_returns_json(self, client):
        """Should return JSON response with admin message."""
        response = client.get("/admin")

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
