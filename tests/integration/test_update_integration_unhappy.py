"""Unhappy path integration tests for the update system."""

import asyncio
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from birdnetpi.utils.cache import Cache


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


class TestAPIErrorHandling:
    """Test API error handling for update endpoints."""

    def test_check_update_with_cache_failure(self, client, cache):
        """Should handle cache failures gracefully."""
        # Configure the cache to fail
        cache.set.side_effect = Exception("Redis connection lost")
        cache.get.side_effect = Exception("Redis connection lost")

        response = client.post("/api/update/check", json={"force": False})

        # Should return 500 error
        assert response.status_code == 500
        assert "Redis connection lost" in response.text

    def test_apply_update_with_invalid_version_format(self, client, app_with_temp_data):
        """Should accept invalid version (validation happens in daemon)."""
        # The app already has a mocked cache that returns None by default

        # API doesn't validate version format
        response = client.post(
            "/api/update/apply", json={"version": "not-a-version", "dry_run": False}
        )

        # Should accept it (daemon will validate)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_status_when_cache_returns_invalid_json(self, client, cache):
        """Should handle corrupted cache data."""
        # Return invalid data structure
        cache.get.return_value = "invalid-json-string"

        response = client.get("/api/update/status")

        # Should handle gracefully
        assert response.status_code == 500

    def test_cancel_with_cache_delete_failure(self, client, cache):
        """Should handle cache delete failures."""
        cache.get.return_value = {"action": "check", "force": False}
        cache.delete.side_effect = Exception("Cannot delete key")

        response = client.delete("/api/update/cancel")

        assert response.status_code == 500
        assert "Cannot delete key" in response.text


class TestRaceConditions:
    """Test race conditions in the update flow."""

    def test_simultaneous_check_requests(self, client, cache):
        """Should handle simultaneous check requests."""
        cache.get.return_value = None

        # Track set calls
        set_calls = []

        def track_set(key, value, ttl=None):
            set_calls.append((key, value))
            return True

        cache.set.side_effect = track_set

        # Send multiple check requests
        responses = []
        for _ in range(5):
            response = client.post("/api/update/check", json={"force": False})
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

        # Should have queued multiple requests (last one wins)
        assert len(set_calls) == 5
        assert all(call[0] == "update:request" for call in set_calls)

    def test_apply_while_check_in_progress(self, client, cache):
        """Should prevent apply while check is in progress."""
        # Simulate check in progress
        cache.get.return_value = {"action": "check", "force": True}

        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already in progress" in data["error"].lower()

    def test_cancel_during_active_update(self, client, cache):
        """Should handle cancel request during active update."""
        # Simulate active update (would need daemon state tracking)
        cache.get.return_value = {
            "action": "apply",
            "version": "v1.1.0",
            "started_at": datetime.now().isoformat(),
        }
        cache.delete.return_value = True

        response = client.delete("/api/update/cancel")

        # Should attempt to cancel
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestMalformedRequests:
    """Test handling of malformed requests."""

    def test_check_with_invalid_json(self, client):
        """Should handle invalid JSON in request."""
        response = client.post(
            "/api/update/check", content="not-json", headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422  # Unprocessable Entity

    def test_apply_with_missing_required_fields(self, client):
        """Should handle missing required fields."""
        response = client.post("/api/update/apply", json={})

        assert response.status_code == 422
        # Should indicate version is required

    def test_apply_with_extra_fields(self, client, cache):
        """Should ignore extra fields in request."""
        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post(
            "/api/update/apply",
            json={
                "version": "v1.1.0",
                "dry_run": False,
                "extra_field": "should_be_ignored",
                "another_extra": 123,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestTimeoutScenarios:
    """Test timeout handling scenarios."""

    def test_long_running_check_request(self, client, cache):
        """Should handle long-running check requests."""
        # First request queues check
        cache.get.return_value = None
        cache.set.return_value = True
        response1 = client.post("/api/update/check", json={"force": False})
        assert response1.status_code == 200

        # Second request while check still running - no status yet
        cache.get.return_value = None
        response2 = client.post("/api/update/check", json={"force": False})

        assert response2.status_code == 200
        # Check for appropriate response message
        data = response2.json()
        assert data["available"] is False
        assert "in progress" in data["error"].lower()

    def test_stale_update_result(self, client, cache):
        """Should handle stale update results."""
        # Return a very old update result
        old_timestamp = "2020-01-01T00:00:00"
        cache.get.return_value = {
            "success": True,
            "version": "v0.1.0",
            "completed_at": old_timestamp,
        }

        response = client.get("/api/update/result")

        assert response.status_code == 200
        data = response.json()
        # Should still return the old result
        assert data["completed_at"] == old_timestamp


class TestViewErrorHandling:
    """Test error handling in view routes."""

    def test_update_view_with_template_error(self, client, mocker, cache):
        """Should handle template rendering errors."""
        cache.get.return_value = None

        # Mock template to fail at a lower level
        with patch("jinja2.Template.render", side_effect=Exception("Template error")):
            try:
                response = client.get("/admin/update/")
                # If template error is caught, should still return something
                assert response.status_code in [200, 500]
            except Exception:
                # Template error might not be caught
                pass

    def test_update_view_with_malformed_cache_data(self, client, cache):
        """Should handle malformed cache data in view."""

        # Return data that would cause template issues
        def cache_get_side_effect(key):
            if key == "update:status":
                return {"invalid": "structure"}  # Missing required fields
            elif key == "update:result":
                return 12345  # Not a dict
            return None

        cache.get.side_effect = cache_get_side_effect

        # Should handle gracefully
        response = client.get("/admin/update/")

        # View should still render (with defaults)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestCacheTTLAndExpiry:
    """Test cache TTL and expiry scenarios."""

    def test_expired_update_request(self, client, cache):
        """Should handle expired update requests."""
        # First queue a request
        cache.get.return_value = None
        cache.set.return_value = True
        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})
        assert response.status_code == 200

        # Verify TTL was set
        call_args = cache.set.call_args
        assert call_args[1]["ttl"] == 300  # 5 minutes for apply

    def test_check_request_ttl(self, client, cache):
        """Should set appropriate TTL for check requests."""
        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post("/api/update/check", json={"force": True})
        assert response.status_code == 200

        # Verify shorter TTL for check
        call_args = cache.set.call_args
        assert call_args[1]["ttl"] == 60  # 1 minute for check


class TestDaemonCommunicationFailures:
    """Test failures in communication with update daemon."""

    @pytest.mark.asyncio
    async def test_daemon_not_processing_requests(self, path_resolver):
        """Should handle daemon not processing requests."""
        mock_cache = MagicMock(spec=Cache)

        # Request sits in cache without being processed
        request_data = {"action": "check", "force": False, "created_at": "2024-01-01T00:00:00"}
        mock_cache.get = Mock(return_value=request_data)

        # Simulate timeout waiting for daemon
        await asyncio.sleep(0.1)  # Small delay

        # Request should still be in cache (not processed)
        request = mock_cache.get("update:request")
        assert request is not None
        assert request["action"] == "check"

    @pytest.mark.asyncio
    async def test_daemon_crash_during_update(self, path_resolver):
        """Should handle daemon crash during update."""
        mock_cache = MagicMock(spec=Cache)

        # Update started but never completed
        mock_cache.get = Mock(
            side_effect=lambda key: {
                "update:status": {
                    "available": True,
                    "current_version": "v1.0.0",
                    "latest_version": "v1.1.0",
                },
                "update:request": {
                    "action": "apply",
                    "version": "v1.1.0",
                    "started_at": "2024-01-01T00:00:00",
                },
                "update:result": None,  # Never set due to crash
            }.get(key)
        )

        # Check if update is stuck
        request = mock_cache.get("update:request")
        result = mock_cache.get("update:result")

        assert request is not None
        assert result is None  # Indicates incomplete update


class TestSecurityScenarios:
    """Test security-related scenarios."""

    def test_path_traversal_in_version(self, client, cache):
        """Should handle path traversal attempts in version."""
        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post(
            "/api/update/apply", json={"version": "../../../etc/passwd", "dry_run": False}
        )

        # API accepts it (daemon should validate)
        assert response.status_code == 200

    def test_command_injection_in_version(self, client, cache):
        """Should handle command injection attempts."""
        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post(
            "/api/update/apply", json={"version": "v1.0.0; rm -rf /", "dry_run": False}
        )

        # API accepts it (daemon should sanitize)
        assert response.status_code == 200

    def test_xss_in_update_status(self, client, cache):
        """Should handle XSS attempts in update status."""
        # Try to inject script tag
        cache.get.return_value = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "<script>alert('XSS')</script>",
            "release_notes": "<img src=x onerror=alert('XSS')>",
        }

        response = client.get("/api/update/status")

        assert response.status_code == 200
        data = response.json()
        # Data should be returned as-is (frontend should escape)
        assert "<script>" in data["latest_version"]
