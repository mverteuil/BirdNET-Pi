"""Simple tests for health check API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_with_temp_data):
    """Create test client."""
    return TestClient(app_with_temp_data)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_root_endpoint(self, client):
        """Test the root health endpoint."""
        response = client.get("/api/health/")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data

        # Status should be healthy
        assert data["status"] == "healthy"

    def test_health_live_endpoint(self, client):
        """Test the liveness endpoint."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "status" in data
        assert data["status"] == "alive"

    def test_health_ready_endpoint(self, client):
        """Test the readiness endpoint."""
        response = client.get("/api/health/ready")

        # Could be 200 (ready) or 503 (not ready)
        assert response.status_code in [200, 503]

        data = response.json()
        assert "status" in data
        assert "checks" in data

        if response.status_code == 200:
            assert data["status"] == "ready"
            assert "database" in data["checks"]
            assert data["checks"]["database"] is True
        else:
            # If not ready, should have error details
            assert data["status"] == "not_ready"
            assert "database" in data["checks"]
            assert data["checks"]["database"] is False

    def test_health_detailed_endpoint(self, client):
        """Test the detailed health endpoint."""
        response = client.get("/api/health/detailed")

        # Could be 200 (healthy) or 503 (unhealthy)
        assert response.status_code in [200, 503]

        data = response.json()

        # Check response structure
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "components" in data  # Changed from "checks" to "components"

        # Status should reflect health
        if response.status_code == 200:
            assert data["status"] == "healthy"
        else:
            assert data["status"] == "unhealthy"

        # Components should be a dict
        assert isinstance(data["components"], dict)

        # Should have database component
        assert "database" in data["components"]

        # Each component should have status
        for _component_name, component_info in data["components"].items():
            assert "status" in component_info
            assert component_info["status"] in ["healthy", "unhealthy", "degraded", "unknown"]


class TestHealthResponseFormat:
    """Test health check response formats."""

    def test_consistent_timestamp_format(self, client):
        """All health endpoints should have consistent timestamp format."""
        endpoints = [
            "/api/health/",
            "/api/health/detailed",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            data = response.json()

            # Should have timestamp
            assert "timestamp" in data

            # Timestamp should be a string (ISO format)
            assert isinstance(data["timestamp"], str)

            # Should be parseable as ISO format
            from datetime import datetime

            try:
                datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"Invalid timestamp format in {endpoint}: {data['timestamp']}")

    def test_version_included(self, client):
        """Version should be included in appropriate endpoints."""
        endpoints_with_version = [
            "/api/health/",
            "/api/health/detailed",
        ]

        for endpoint in endpoints_with_version:
            response = client.get(endpoint)
            data = response.json()

            # Should have version
            assert "version" in data

            # Version should be a string
            assert isinstance(data["version"], str)

            # Version should not be empty
            assert len(data["version"]) > 0


class TestHealthDatabaseCheck:
    """Test database health checks."""

    def test_ready_endpoint_checks_database(self, client):
        """Ready endpoint should check database connectivity."""
        response = client.get("/api/health/ready")
        data = response.json()

        # Should have checks with database status
        assert "checks" in data
        assert "database" in data["checks"]

        # If ready, database check passed
        if response.status_code == 200:
            assert data["checks"]["database"] is True

        # If not ready, database check failed
        elif response.status_code == 503:
            assert data["checks"]["database"] is False

    def test_detailed_endpoint_includes_database(self, client):
        """Detailed endpoint should include database check."""
        response = client.get("/api/health/detailed")

        data = response.json()

        # Should have database in components
        assert "components" in data
        assert "database" in data["components"]

        db_component = data["components"]["database"]
        assert "status" in db_component

        # If healthy, should have type field
        if db_component["status"] == "healthy":
            assert "type" in db_component
            assert db_component["type"] == "sqlite"


class TestHealthErrorHandling:
    """Test error handling in health checks."""

    def test_health_endpoints_handle_errors_gracefully(self, client):
        """Health endpoints should never crash the application."""
        endpoints = [
            "/api/health/",
            "/api/health/live",
            "/api/health/ready",
            "/api/health/detailed",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)

            # Should always return a valid HTTP status
            assert response.status_code in [200, 503]

            # Should always return JSON
            assert response.headers.get("content-type") == "application/json"

            # Should always have a parseable JSON response
            try:
                data = response.json()
                assert isinstance(data, dict)
            except Exception as e:
                pytest.fail(f"Failed to parse JSON from {endpoint}: {e}")

    def test_invalid_health_endpoint_returns_404(self, client):
        """Invalid health endpoints should return 404."""
        invalid_endpoints = [
            "/api/health/invalid",
            "/api/health/nonexistent",
            "/api/health/test",
        ]

        for endpoint in invalid_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 404
