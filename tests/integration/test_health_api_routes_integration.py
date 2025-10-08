"""Integration tests for health check API endpoints.

These tests verify that health endpoints work correctly with real components,
including database connectivity and file system access.
"""

import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def client(app_with_temp_data):
    """Create test client using the global app fixture."""
    return TestClient(app_with_temp_data)


class TestHealthEndpointsIntegration:
    """Integration tests for all health endpoints with real components."""

    def test_health_check_reads_real_version(self, client, repo_root):
        """Should health check reads version from actual pyproject.toml."""
        response = client.get("/api/health/")
        assert response.status_code == 200
        data = response.json()

        # Should read real version from pyproject.toml
        assert "version" in data
        assert data["version"] != "unknown"
        # Version should match pattern like "2.0.0a" or similar
        assert "." in data["version"]  # Has version dots

    def test_all_health_endpoints_with_real_database(self, client):
        """Should all health endpoints work with real database connection."""
        # Test basic health endpoint
        response = client.get("/api/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "birdnet-pi"
        assert "timestamp" in data

        # Test liveness - should always work
        response = client.get("/api/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

        # Test readiness with real database
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] is True
        assert "version" in data["checks"]
        assert "timestamp" in data

        # Test detailed health with real database
        response = client.get("/api/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "components" in data
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["database"]["type"] == "sqlite"
        assert data["components"]["cache"]["status"] in ["healthy", "unknown"]


class TestHealthEndpointsDatabaseFailure:
    """Test health endpoints when database is unavailable."""

    def test_readiness_with_database_error(self, tmp_path, path_resolver):
        """Should readiness probe when database connection fails."""
        # Create a mock database service that simulates connection failure
        mock_db_service = MagicMock(spec=CoreDatabaseService)
        mock_db_service.async_engine = AsyncMock(spec=AsyncEngine)  # Add async_engine for sqladmin

        # Create a mock session context manager that raises an error
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = OperationalError(
            "Cannot connect to database", None, None
        )
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mock_db_service.get_async_db.return_value = mock_session

        # Override the container's database service BEFORE creating app
        Container.core_database.override(providers.Singleton(lambda: mock_db_service))
        Container.path_resolver.override(providers.Singleton(lambda: path_resolver))

        try:
            # Patch sqladmin setup to avoid issues
            with patch("birdnetpi.web.routers.sqladmin_view_routes.setup_sqladmin", autospec=True):
                # Create app with the mocked database
                app = create_app()

            with TestClient(app) as client:
                response = client.get("/api/health/ready")

                # Should return 503 when database is not accessible
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "not_ready"
                assert data["checks"]["database"] is False
                assert "timestamp" in data
        finally:
            Container.core_database.reset_override()
            Container.path_resolver.reset_override()

    def test_detailed_health_with_database_error(self, tmp_path, path_resolver):
        """Should detailed health check when database fails."""
        # Create a mock database service that simulates query failure
        mock_db_service = MagicMock(spec=CoreDatabaseService)
        mock_db_service.async_engine = AsyncMock(spec=AsyncEngine)  # Add async_engine for sqladmin

        # Create a mock session that fails
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = Exception("Database is locked")
        # __aenter__ and __aexit__ must be AsyncMocks to be awaitable in async context managers
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mock_db_service.get_async_db.return_value = mock_session

        # Override the container's database service BEFORE creating app
        Container.core_database.override(providers.Singleton(lambda: mock_db_service))
        Container.path_resolver.override(providers.Singleton(lambda: path_resolver))

        try:
            # Patch sqladmin setup to avoid issues
            with patch("birdnetpi.web.routers.sqladmin_view_routes.setup_sqladmin", autospec=True):
                # Create app with the mocked database
                app = create_app()

            with TestClient(app) as client:
                response = client.get("/api/health/detailed")

                # Should return 503 with degraded status
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "degraded"
                assert data["components"]["database"]["status"] == "unhealthy"
                assert "error" in data["components"]["database"]
                # Error message should indicate the problem
                assert (
                    "database" in data["components"]["database"]["error"].lower()
                    or "locked" in data["components"]["database"]["error"].lower()
                )
        finally:
            Container.core_database.reset_override()
            Container.path_resolver.reset_override()


class TestHealthEndpointsVersionHandling:
    """Test version handling in health endpoints."""

    def test_health_with_missing_pyproject_file(self, client):
        """Should health check when pyproject.toml is not found."""
        # Mock both Path.exists() and open() to simulate missing file
        with (
            patch("birdnetpi.web.routers.health_api_routes.Path", autospec=True) as mock_path,
            patch("builtins.open", side_effect=FileNotFoundError("pyproject.toml not found")),
        ):
            # Make both paths not exist
            mock_path.return_value.exists.return_value = False

            response = client.get("/api/health/")
            assert response.status_code == 200
            data = response.json()
            # Should fall back to "unknown" when file doesn't exist
            assert data["version"] == "unknown"
            # Other fields should still work
            assert data["status"] == "healthy"
            assert data["service"] == "birdnet-pi"

    def test_health_with_malformed_pyproject(self, client):
        """Should health check with malformed pyproject.toml."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as tf:
            # Write invalid TOML
            tf.write("This is not valid TOML {]{[}")
            tf.flush()
            temp_path = tf.name

        try:
            with patch("birdnetpi.web.routers.health_api_routes.Path", autospec=True) as mock_path:
                # Create a mock Path object
                mock_path_instance = MagicMock(spec=Path)
                mock_path_instance.exists.return_value = True
                mock_path_instance.open.return_value.__enter__.return_value.read.return_value = (
                    b"This is not valid TOML {]{[}"
                )

                # Return our mock path instance
                mock_path.return_value = mock_path_instance

                response = client.get("/api/health/")
                assert response.status_code == 200
                data = response.json()
                # Should return "unknown" when TOML parsing fails
                assert data["version"] == "unknown"
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestHealthEndpointsConsistency:
    """Test consistency across health endpoints."""

    def test_version_consistent_across_endpoints(self, client):
        """Should have consistent version across all endpoints that include it."""
        # Get version from main health endpoint
        response = client.get("/api/health/")
        main_version = response.json()["version"]

        # Check readiness endpoint
        response = client.get("/api/health/ready")
        ready_version = response.json()["checks"]["version"]
        assert ready_version == main_version

        # Check detailed endpoint
        response = client.get("/api/health/detailed")
        detailed_version = response.json()["version"]
        assert detailed_version == main_version

    def test_timestamp_format_consistency(self, client):
        """Should have timestamps in consistent ISO format."""
        endpoints = [
            "/api/health/",
            "/api/health/ready",
            "/api/health/detailed",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            data = response.json()

            if "timestamp" in data:
                timestamp = data["timestamp"]
                # Should end with 'Z' for UTC
                assert timestamp.endswith("Z")
                # Should be parseable as ISO format
                # Remove 'Z' and add '+00:00' for Python's fromisoformat
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_status_codes_match_health_status(self, client):
        """Should HTTP status codes align with health status."""
        # Healthy endpoints should return 200
        response = client.get("/api/health/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

        response = client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

        # Ready endpoint should be 200 when ready
        response = client.get("/api/health/ready")
        if response.status_code == 200:
            assert response.json()["status"] == "ready"
        elif response.status_code == 503:
            assert response.json()["status"] == "not_ready"

        # Detailed should be 200 when healthy
        response = client.get("/api/health/detailed")
        if response.status_code == 200:
            assert response.json()["status"] == "healthy"
        elif response.status_code == 503:
            assert response.json()["status"] in ["degraded", "unhealthy"]


class TestHealthEndpointsPerformance:
    """Test performance characteristics of health endpoints."""

    def test_health_endpoints_are_fast(self, client):
        """Should health endpoints respond quickly."""
        endpoints = [
            "/api/health/",
            "/api/health/live",
            "/api/health/ready",
            "/api/health/detailed",
        ]

        for endpoint in endpoints:
            start = time.time()
            response = client.get(endpoint)
            duration = time.time() - start

            # Health checks should be fast (under 1 second)
            assert duration < 1.0, f"{endpoint} took {duration:.2f}s"
            # Should still return valid response
            assert response.status_code in [200, 503]
            assert response.json() is not None

    def test_liveness_is_lightweight(self, client):
        """Should liveness probe is very lightweight."""
        # Run multiple times to ensure consistency
        durations = []
        for _ in range(5):
            start = time.time()
            response = client.get("/api/health/live")
            durations.append(time.time() - start)
            assert response.status_code == 200

        # Liveness should be extremely fast (under 100ms on average)
        avg_duration = sum(durations) / len(durations)
        assert avg_duration < 0.1, f"Liveness average: {avg_duration:.3f}s"
