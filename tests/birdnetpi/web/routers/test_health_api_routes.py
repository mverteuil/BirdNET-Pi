"""Tests for health check API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_with_temp_data):
    """Create test client."""
    return TestClient(app_with_temp_data)


class TestHealthEndpoint:
    """Test /health endpoint."""

    @pytest.mark.parametrize(
        "expected_fields,additional_checks",
        [
            pytest.param(
                ["status", "timestamp", "version", "service"],
                lambda data: data["status"] == "healthy" and data["service"] == "birdnet-pi",
                id="basic_health_check",
            ),
        ],
    )
    def test_health_endpoint(self, client, expected_fields, additional_checks):
        """Should return proper health check format with all required fields."""
        response = client.get("/api/health/")

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields present
        for field in expected_fields:
            assert field in data

        # Run additional checks
        assert additional_checks(data)

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

    def test_liveness_endpoint(self, client):
        """Should return alive status with proper format."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "status" in data
        # Status should be alive for liveness
        assert data["status"] == "alive"


class TestReadinessEndpoint:
    """Test /readiness endpoint."""

    def test_readiness_endpoint(self, client):
        """Should return readiness status with all required checks."""
        response = client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data
        assert data["status"] in ["ready", "not_ready"]

        # Check all required services
        checks = data["checks"]
        assert "database" in checks
        assert "version" in checks

        # Validate check types
        assert isinstance(checks["database"], bool)
        assert data["checks"]["database"] in [True, False]


class TestDetailedHealthEndpoint:
    """Test /health/detailed endpoint."""

    def test_detailed_health_endpoint(self, client):
        """Should return detailed health information with all components and metadata."""
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

        # Validate all component statuses
        for _component_name, component_data in data["components"].items():
            assert "status" in component_data
            assert component_data["status"] in ["healthy", "unhealthy", "unknown", "degraded"]

        # Validate service metadata
        assert data["service"] == "birdnet-pi"
        assert isinstance(data["version"], str)
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
