"""Integration tests for log router that exercise real log service."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.web.routers.log_router import router


@pytest.fixture
def app_with_log_router():
    """Create FastAPI app with log router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_log_router):
    """Create test client with real app."""
    return TestClient(app_with_log_router)


class TestLogRouterIntegration:
    """Integration tests for log router with real log service."""

    def test_log_endpoint_returns_plain_text(self, client):
        """Should return plain text response with log content."""
        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = "Test log content\nSecond line\nThird line"

            response = client.get("/log")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert response.text == "Test log content\nSecond line\nThird line"
            mock_get_logs.assert_called_once()

    def test_log_endpoint_handles_empty_logs(self, client):
        """Should handle empty log content gracefully."""
        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = ""

            response = client.get("/log")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert response.text == ""
            mock_get_logs.assert_called_once()

    def test_log_endpoint_creates_log_service_instance(self, client):
        """Should create LogService instance for each request."""
        with patch("birdnetpi.web.routers.log_router.LogService") as mock_log_service:
            mock_instance = MagicMock()
            mock_instance.get_logs.return_value = "Mock log data"
            mock_log_service.return_value = mock_instance

            response = client.get("/log")

            assert response.status_code == 200
            # Should have created a new LogService instance
            mock_log_service.assert_called_once()
            mock_instance.get_logs.assert_called_once()
            assert response.text == "Mock log data"

    def test_log_endpoint_handles_log_service_errors(self, client):
        """Should handle LogService errors appropriately."""
        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.side_effect = Exception("Log service error")

            # The endpoint should handle the error gracefully
            response = client.get("/log")

            # Should return 500 with plain text error message
            assert response.status_code == 500
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert "Error retrieving logs: Log service error" in response.text

    def test_log_endpoint_returns_multiline_content(self, client):
        """Should handle multiline log content correctly."""
        log_content = """2025-01-15 10:30:00 INFO: Service started
2025-01-15 10:30:05 DEBUG: Processing detection
2025-01-15 10:30:10 ERROR: Failed to connect to database
2025-01-15 10:30:15 INFO: Retrying connection
2025-01-15 10:30:20 INFO: Connection restored"""

        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = log_content

            response = client.get("/log")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert response.text == log_content
            # Check that multiline content is preserved
            assert response.text.count("\n") == 4  # 5 lines = 4 newlines

    def test_log_endpoint_handles_large_logs(self, client):
        """Should handle large log content without issues."""
        # Create a large log content (simulate 1000 lines)
        large_log_content = "\n".join(
            [f"2025-01-15 10:30:{i:02d} INFO: Log line {i}" for i in range(1000)]
        )

        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = large_log_content

            response = client.get("/log")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert len(response.text.split("\n")) == 1000
            assert "Log line 0" in response.text
            assert "Log line 999" in response.text

    def test_log_endpoint_uses_plain_text_response_class(self, client):
        """Should use PlainTextResponse class for proper content type."""
        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = "Test content"

            response = client.get("/log")

            assert response.status_code == 200
            # Should specifically be plain text, not HTML or JSON
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert not response.headers["content-type"].startswith("text/html")
            assert not response.headers["content-type"].startswith("application/json")

    def test_log_endpoint_integration_with_real_log_service(self, client):
        """Should integrate with real LogService class."""
        # This test uses the real LogService without mocking to test integration
        response = client.get("/log")

        # Should succeed regardless of log content (may be empty or have actual logs)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        # Content can be empty or contain actual logs - both are valid
        assert isinstance(response.text, str)

    def test_log_endpoint_handles_unicode_content(self, client):
        """Should handle unicode characters in log content."""
        unicode_log_content = (
            "2025-01-15 10:30:00 INFO: Species detected: Tōkai-tehi (Japanese Robin) 🐦"
        )

        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = unicode_log_content

            response = client.get("/log")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert response.text == unicode_log_content
            assert "🐦" in response.text
            assert "Tōkai-tehi" in response.text

    def test_log_endpoint_preserves_formatting(self, client):
        """Should preserve log formatting including tabs and spaces."""
        formatted_log_content = """2025-01-15 10:30:00 INFO:    Service started
2025-01-15 10:30:05 DEBUG:  	Processing with tabs
2025-01-15 10:30:10 ERROR:        Multiple spaces preserved"""

        with patch("birdnetpi.web.routers.log_router.LogService.get_logs") as mock_get_logs:
            mock_get_logs.return_value = formatted_log_content

            response = client.get("/log")

            assert response.status_code == 200
            assert response.text == formatted_log_content
            # Check that formatting is preserved
            assert "    Service started" in response.text  # Multiple spaces
            assert "  	Processing with tabs" in response.text  # Tab character
            assert "        Multiple spaces preserved" in response.text  # More spaces
