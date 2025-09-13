"""Tests for health check API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_with_temp_data):
    """Create test client."""
    return TestClient(app_with_temp_data)


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_check_success(self, client):
        """Should return healthy status when all checks pass."""
        response = client.get("/api/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert "service" in data

    def test_health_check_format(self, client):
        """Should return proper health check format."""
        response = client.get("/api/health/")

        data = response.json()

        # Check response structure for basic health endpoint
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "service" in data
        assert data["service"] == "birdnet-pi"

    def test_health_check_database_included(self, client):
        """Should include database check in detailed health status."""
        response = client.get("/api/health/detailed")

        data = response.json()

        # Should have components in detailed endpoint
        assert "components" in data
        # Should have database component
        assert "database" in data["components"]
        assert data["components"]["database"]["status"] in ["healthy", "unhealthy"]


class TestLivenessEndpoint:
    """Test /liveness endpoint."""

    def test_liveness_check(self, client):
        """Should return alive status."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_liveness_format(self, client):
        """Should return proper liveness format."""
        response = client.get("/api/health/live")

        data = response.json()

        # Check required fields
        assert "status" in data

        # Status should be alive for liveness
        assert data["status"] == "alive"


class TestReadinessEndpoint:
    """Test /readiness endpoint."""

    def test_readiness_check_success(self, client):
        """Should return ready when all services are available."""
        response = client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ready", "not_ready"]
        assert "checks" in data
        assert data["checks"]["database"] in [True, False]

    def test_readiness_check_format(self, client):
        """Should return proper readiness format."""
        response = client.get("/api/health/ready")

        data = response.json()

        # Check structure
        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data

        # Checks should include database
        assert "database" in data["checks"]
        assert isinstance(data["checks"]["database"], bool)

    def test_readiness_includes_all_services(self, client):
        """Should check all required services."""
        response = client.get("/api/health/ready")

        data = response.json()
        checks = data["checks"]

        # Should check core services
        assert "database" in checks
        assert "version" in checks

        # Database should be boolean
        assert isinstance(checks["database"], bool)


class TestDetailedHealthEndpoint:
    """Test /health/detailed endpoint."""

    def test_detailed_health_check(self, client):
        """Should return detailed health information."""
        response = client.get("/api/health/detailed")

        # Should return 200 or 503 depending on health
        assert response.status_code in [200, 503]
        data = response.json()

        # Check structure
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert "version" in data
        assert "service" in data

        # Check components exist
        assert "database" in data["components"]
        assert "cache" in data["components"]

        # Check database component
        db_component = data["components"]["database"]
        assert "status" in db_component
        assert db_component["status"] in ["healthy", "unhealthy"]

    def test_detailed_health_check_fields(self, client):
        """Should include all required fields in components."""
        response = client.get("/api/health/detailed")

        data = response.json()

        # Each component should have required fields
        for _component_name, component_data in data["components"].items():
            assert "status" in component_data
            assert component_data["status"] in ["healthy", "unhealthy", "unknown", "degraded"]

        # Should have service name
        assert data["service"] == "birdnet-pi"

    def test_detailed_health_system_info(self, client):
        """Should include version information."""
        response = client.get("/api/health/detailed")

        data = response.json()

        # Should have version
        assert "version" in data
        assert isinstance(data["version"], str)

        # Should have timestamp
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)


class TestHealthCheckEndpoints:
    """Test various health check endpoints."""

    def test_all_health_endpoints_exist(self, client):
        """Should have all standard health endpoints."""
        endpoints = [
            "/api/health/",
            "/api/health/live",
            "/api/health/ready",
            "/api/health/detailed",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not return 404
            assert response.status_code != 404, f"Endpoint {endpoint} not found"
            # Should return JSON
            assert response.headers["content-type"] == "application/json"

    def test_health_endpoint_consistency(self, client):
        """Should have consistent response format across endpoints."""
        # Test basic health endpoints
        for endpoint in ["/api/health/", "/api/health/live", "/api/health/ready"]:
            response = client.get(endpoint)
            data = response.json()

            # All should have status
            assert "status" in data
            # ready and root have timestamp
            if endpoint != "/api/health/live":
                assert "timestamp" in data
