"""Tests for update API routes."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_with_temp_data, authenticate_sync_client):
    """Create authenticated test client from app."""
    test_client = TestClient(app_with_temp_data)
    authenticate_sync_client(test_client)
    return test_client


class TestCheckForUpdates:
    """Test /api/update/check endpoint."""

    def test_check_for_updates_success(self, client, cache):
        """Should queue update check and return status."""
        # Get the existing cache mock from the container
        # Use cache fixture
        # Cache provided by fixture

        # Configure the mock for this test
        cache.get.return_value = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "release_notes": "New features",
            "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
            "can_auto_update": True,
        }
        cache.set.return_value = True

        response = client.post("/api/update/check", json={"force": False})

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["current_version"] == "v1.0.0"
        assert data["latest_version"] == "v1.1.0"

        # Should have queued the request
        cache.set.assert_called()
        call_args = cache.set.call_args
        assert call_args[0][0] == "update:request"
        assert call_args[0][1]["action"] == "check"

    def test_check_for_updates_force(self, client, cache):
        """Should force update check when requested."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post("/api/update/check", json={"force": True})

        assert response.status_code == 200

        # Should queue with force flag
        cache.set.assert_called()
        call_args = cache.set.call_args
        assert call_args[0][1]["force"] is True

    def test_check_for_updates_no_status(self, client, cache):
        """Should return in-progress message when no cached status."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None  # No cached status

        response = client.post("/api/update/check", json={"force": False})

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "in progress" in data["error"].lower()


class TestGetUpdateStatus:
    """Test /api/update/status endpoint."""

    def test_get_update_status_available(self, client, cache):
        """Should return cached update status when available."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "release_notes": "Bug fixes",
            "release_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
            "can_auto_update": True,
        }

        response = client.get("/api/update/status")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["current_version"] == "v1.0.0"
        assert data["latest_version"] == "v1.1.0"
        assert data["release_notes"] == "Bug fixes"

    def test_get_update_status_not_available(self, client, cache):
        """Should return no update message when no status cached."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None

        response = client.get("/api/update/status")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "No update status available" in data["error"]


class TestApplyUpdate:
    """Test /api/update/apply endpoint."""

    def test_apply_update_success(self, client, cache):
        """Should queue update application."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None  # No existing request
        cache.set.return_value = True

        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "v1.1.0" in data["message"]
        assert "queued" in data["message"].lower()

        # Should queue the update request
        cache.set.assert_called()
        call_args = cache.set.call_args
        assert call_args[0][0] == "update:request"
        assert call_args[0][1]["action"] == "apply"
        assert call_args[0][1]["version"] == "v1.1.0"
        assert call_args[0][1]["dry_run"] is False

    def test_apply_update_dry_run(self, client, cache):
        """Should support dry run mode."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None
        cache.set.return_value = True

        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": True})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Should include dry_run flag
        call_args = cache.set.call_args
        assert call_args[0][1]["dry_run"] is True

    def test_apply_update_already_in_progress(self, client, cache):
        """Should reject if update already in progress."""
        # Use cache fixture
        # Cache provided by fixture

        # Existing update request
        cache.get.return_value = {"action": "apply", "version": "v1.0.5"}

        response = client.post("/api/update/apply", json={"version": "v1.1.0", "dry_run": False})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already in progress" in data["error"].lower()


class TestGetUpdateResult:
    """Test /api/update/result endpoint."""

    def test_get_update_result_success(self, client, cache):
        """Should return successful update result."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = {
            "success": True,
            "version": "v1.1.0",
            "completed_at": "2024-01-01T12:00:00",
        }

        response = client.get("/api/update/result")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["version"] == "v1.1.0"
        assert data["completed_at"] == "2024-01-01T12:00:00"

    def test_get_update_result_failure(self, client, cache):
        """Should return failed update result."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = {
            "success": False,
            "error": "Dependencies failed to install",
            "version": "v1.1.0",
        }

        response = client.get("/api/update/result")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Dependencies failed to install"
        assert data["version"] == "v1.1.0"

    def test_get_update_result_no_result(self, client, cache):
        """Should handle no result available."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None

        response = client.get("/api/update/result")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "No update result available" in data["error"]


class TestCancelUpdate:
    """Test /api/update/cancel endpoint."""

    def test_cancel_update_check_request(self, client, cache):
        """Should cancel pending check request."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = {"action": "check", "force": False}
        cache.delete.return_value = True

        response = client.delete("/api/update/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Check request cancelled" in data["message"]

        # Should delete the request
        cache.delete.assert_called_with("update:request")

    def test_cancel_update_apply_request(self, client, cache):
        """Should cancel pending apply request."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = {"action": "apply", "version": "v1.1.0"}
        cache.delete.return_value = True

        response = client.delete("/api/update/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Update request cancelled" in data["message"]

        cache.delete.assert_called_with("update:request")

    def test_cancel_update_no_request(self, client, cache):
        """Should handle no request to cancel."""
        # Use cache fixture
        # Cache provided by fixture

        cache.get.return_value = None

        response = client.delete("/api/update/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "No update request to cancel" in data["error"]


class TestUpdateAPIIntegration:
    """Test update API integration scenarios."""

    def test_update_flow_check_then_apply(self, client, cache):
        """Should support check then apply flow."""
        # Use cache fixture
        # Cache provided by fixture

        # First check for updates
        cache.get.return_value = {
            "available": True,
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "can_auto_update": True,
        }

        check_response = client.post("/api/update/check", json={"force": False})
        assert check_response.status_code == 200
        assert check_response.json()["available"] is True

        # Then apply the update
        cache.get.return_value = None  # Clear for apply
        apply_response = client.post(
            "/api/update/apply", json={"version": "v1.1.0", "dry_run": False}
        )
        assert apply_response.status_code == 200
        assert apply_response.json()["success"] is True

        # Finally check result
        cache.get.return_value = {"success": True, "version": "v1.1.0"}
        result_response = client.get("/api/update/result")
        assert result_response.status_code == 200
        assert result_response.json()["success"] is True

    def test_all_update_endpoints_exist(self, app_with_temp_data, authenticate_sync_client):
        """Should have all update endpoints available."""
        client = TestClient(app_with_temp_data)
        authenticate_sync_client(client)

        endpoints = [
            ("/api/update/status", "GET"),
            ("/api/update/check", "POST"),
            ("/api/update/apply", "POST"),
            ("/api/update/result", "GET"),
            ("/api/update/cancel", "DELETE"),
        ]

        for endpoint, method in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            elif method == "DELETE":
                response = client.delete(endpoint)
            else:
                continue  # Skip unknown methods

            # Should not return 404
            assert response.status_code != 404, f"Endpoint {endpoint} ({method}) not found"
            # Should return JSON
            assert response.headers.get("content-type") == "application/json"
