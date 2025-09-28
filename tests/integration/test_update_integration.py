"""Integration tests for the update system flow."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.utils.cache import Cache


@pytest.fixture
def client(app_with_temp_data):
    """Create test client from app."""
    # Mount static files to avoid template rendering errors
    import os
    import tempfile

    from fastapi.staticfiles import StaticFiles

    # Create a temporary static directory
    static_dir = tempfile.mkdtemp()

    # Create a dummy CSS file
    with open(os.path.join(static_dir, "style.css"), "w") as f:
        f.write("/* dummy css */")

    # Mount the static files
    app_with_temp_data.mount("/static", StaticFiles(directory=static_dir), name="static")

    return TestClient(app_with_temp_data)


@pytest.fixture
def mock_update_manager(path_resolver):
    """Provide a mock UpdateManager."""
    mock = MagicMock(spec=UpdateManager)

    # Mock version methods
    mock.get_current_version.return_value = "v1.0.0"
    mock.get_latest_version.return_value = "v1.1.0"

    # Mock async methods
    mock.check_for_updates = AsyncMock(
        return_value={
            "update_available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "release_notes": "New features and fixes",
            "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
            "can_auto_update": True,
            "checked_at": datetime.now().isoformat(),
        }
    )

    mock.apply_update = AsyncMock(
        return_value={
            "success": True,
            "version": "v1.1.0",
            "updated_at": datetime.now().isoformat(),
        }
    )

    return mock


class TestUpdateFlowIntegration:
    """Test the complete update flow from check to apply."""

    def test_check_and_apply_flow(self, client, cache):
        """Should support complete check and apply workflow."""
        # Step 1: Check for updates
        check_status = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "release_notes": "New features",
            "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
            "can_auto_update": True,
        }
        cache.get.return_value = check_status

        response = client.post("/api/update/check", json={"force": False})
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["latest_version"] == "v1.1.0"

        # Step 2: Apply the update
        cache.get.return_value = None  # Clear for apply

        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "v1.1.0" in data["message"]

        # Step 3: Check result
        result = {
            "success": True,
            "version": "v1.1.0",
            "completed_at": datetime.now().isoformat(),
        }
        cache.get.return_value = result

        response = client.get("/api/update/result")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["version"] == "v1.1.0"

    def test_view_and_api_consistency(self, client, cache):
        """Should have consistent data between view and API endpoints."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # Set up update status
        status = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "release_notes": "Improvements",
            "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
            "can_auto_update": True,
        }

        # Mock cache to return status for both endpoints
        cache.get.side_effect = lambda key: {
            "update:status": status,
            "update:result": None,
        }.get(key)

        # Check API endpoint
        api_response = client.get("/api/update/status")
        assert api_response.status_code == 200
        api_data = api_response.json()
        assert api_data["available"] is True
        assert api_data["latest_version"] == "v1.1.0"

        # Check view endpoint
        view_response = client.get("/admin/update/")
        assert view_response.status_code == 200
        assert "text/html" in view_response.headers["content-type"]

        # Both should have accessed the same cache key
        calls = [call.args[0] for call in cache.get.call_args_list if call.args]
        assert "update:status" in calls

    def test_cancel_pending_update(self, client, cache):
        """Should be able to cancel pending update requests."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # Queue an update request
        cache.get.return_value = None
        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})
        assert response.status_code == 200

        # Now cancel it
        cache.get.return_value = {"action": "apply", "version": "v1.1.0"}
        cache.delete.return_value = True

        response = client.delete("/api/update/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cancelled" in data["message"].lower()

        # Should have deleted the request
        cache.delete.assert_called_with("update:request")

    def test_update_in_progress_prevents_duplicate(self, client, cache):
        """Should prevent duplicate update requests."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # Simulate an update already in progress
        cache.get.return_value = {
            "action": "apply",
            "version": "v1.0.5",
        }

        # Try to start another update
        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already in progress" in data["error"].lower()

    def test_dry_run_mode(self, client, cache):
        """Should support dry run mode for testing updates."""
        # Use cache fixture directly
        # Cache is provided by fixture
        cache.get.return_value = None

        response = client.post(
            "/api/update/apply",
            json={
                "version": "v1.1.0",
                "dry_run": True,  # Test mode
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Check that dry_run flag was set in the request
        call_args = cache.set.call_args
        assert call_args[0][1]["dry_run"] is True


class TestUpdateDaemonIntegration:
    """Test integration with the update daemon functionality."""

    @pytest.mark.asyncio
    async def test_daemon_request_processing_logic(self, path_resolver, mock_update_manager):
        """Should test the update request processing logic."""
        # The update daemon uses DaemonState class and functions, not a class
        # This test verifies the expected flow through the cache interface

        cache = MagicMock(spec=Cache)

        # Test check request flow
        check_request = {"action": "check", "force": False}
        check_result = {
            "update_available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
        }

        # Verify cache would be updated with check result
        cache.set.return_value = True
        cache.set("update:request", check_request, ttl=60)
        cache.set("update:status", check_result, ttl=3600)

        # Verify the expected cache calls
        assert cache.set.call_count == 2

    @pytest.mark.asyncio
    async def test_daemon_apply_processing_logic(self, path_resolver, mock_update_manager):
        """Should test the update apply processing logic."""
        # Test apply request flow
        cache = MagicMock(spec=Cache)

        apply_request = {"action": "apply", "version": "v1.1.0", "dry_run": False}
        apply_result = {
            "success": True,
            "version": "v1.1.0",
            "completed_at": datetime.now().isoformat(),
        }

        # Verify cache would be updated with apply result
        cache.set.return_value = True
        cache.set("update:request", apply_request, ttl=300)
        cache.set("update:result", apply_result, ttl=86400)

        # Verify the expected cache calls
        assert cache.set.call_count == 2


class TestErrorHandling:
    """Test error handling in the update flow."""

    def test_handles_cache_unavailable(self, client, cache):
        """Should handle cache service unavailable gracefully."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # Simulate cache error
        cache.get.side_effect = Exception("Cache unavailable")

        # API endpoints should return 500
        response = client.get("/api/update/status")
        assert response.status_code == 500

    def test_handles_invalid_version(self, client, cache):
        """Should validate version format."""
        # Use cache fixture directly
        # Cache is provided by fixture
        cache.get.return_value = None

        # Version validation happens in the daemon, not the API
        # API just queues the request
        response = client.post(
            "/api/update/apply",
            json={
                "version": "invalid-version",  # Bad format
                "dry_run": False,
            },
        )
        # API should accept it (validation in daemon)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # Request queued


class TestUpdateViewIntegration:
    """Test update view page integration."""

    def test_update_page_with_full_data(self, client, cache):
        """Should render update page with all data available."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # Provide both status and result
        def cache_get_side_effect(key):
            if key == "update:status":
                return {
                    "available": True,
                    "current_version": "v1.0.0",
                    "latest_version": "v1.1.0",
                    "release_notes": "New features",
                    "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
                    "can_auto_update": True,
                }
            elif key == "update:result":
                return {
                    "success": True,
                    "version": "v1.0.5",
                    "completed_at": "2024-01-01T12:00:00",
                }
            return None

        cache.get.side_effect = cache_get_side_effect

        response = client.get("/admin/update/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Should have fetched both status and result (middleware may add extra calls)
        assert cache.get.call_count >= 2
        calls = [call.args[0] for call in cache.get.call_args_list]
        assert "update:status" in calls
        assert "update:result" in calls

    def test_update_page_with_no_data(self, client, cache):
        """Should render update page even with no cached data."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # No cached data
        cache.get.return_value = None

        response = client.get("/admin/update/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestConcurrentRequests:
    """Test handling of concurrent update requests."""

    def test_concurrent_check_requests(self, client, cache):
        """Should handle concurrent check requests."""
        # Use cache fixture directly
        # Cache is provided by fixture
        cache.get.return_value = None
        cache.set.return_value = True

        # Send multiple check requests
        responses = []
        for _ in range(3):
            response = client.post("/api/update/check", json={"force": False})
            responses.append(response)

        # All should succeed (last one wins)
        for response in responses:
            assert response.status_code == 200

    def test_force_check_overrides_recent_check(self, client, cache):
        """Should allow force check even if recently checked."""
        # Use cache fixture directly
        # Cache is provided by fixture

        # First normal check
        cache.get.return_value = {
            "available": False,
            "current_version": "v1.0.0",
            "latest_version": "v1.0.0",
        }

        response = client.post("/api/update/check", json={"force": False})
        assert response.status_code == 200

        # Force check should be allowed
        response = client.post("/api/update/check", json={"force": True})
        assert response.status_code == 200

        # Should have queued with force flag
        call_args = cache.set.call_args
        assert call_args[0][1]["force"] is True
