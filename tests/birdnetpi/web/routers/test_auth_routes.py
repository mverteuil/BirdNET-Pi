"""Tests for authentication routes including SQLAdmin redirects."""

from unittest.mock import MagicMock

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.utils.auth import AuthService
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def client_with_admin(app_with_temp_data):
    """Create a test client with admin authentication mocked.

    This fixture mocks the auth_service to report that an admin user exists,
    which prevents the SetupRedirectMiddleware from redirecting all requests
    to /admin/setup.

    Uses app_with_temp_data fixture to ensure proper path isolation, then
    creates a new app with mocked auth_service that reports admin exists.
    """
    # Mock auth_service to always return True for admin_exists()
    mock_auth_service = MagicMock(spec=AuthService)
    mock_auth_service.admin_exists.return_value = True

    # Override Container's auth_service before app creation
    Container.auth_service.override(providers.Singleton(lambda: mock_auth_service))

    # Create new app with mocked auth (path_resolver and config already overridden)
    app = create_app()

    yield TestClient(app)

    # Reset override
    Container.auth_service.reset_override()


class TestSQLAdminRedirects:
    """Test that SQLAdmin login/logout routes redirect to BirdNET-Pi authentication."""

    def test_sqladmin_login_get_redirects_to_birdnetpi_login(self, client_with_admin):
        """Should redirect GET /admin/database/login to BirdNET-Pi login with next parameter."""
        response = client_with_admin.get("/admin/database/login", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?next=/admin/database"

    def test_sqladmin_login_post_redirects_to_birdnetpi_login(self, client_with_admin):
        """Should redirect POST /admin/database/login to BirdNET-Pi login with next parameter."""
        response = client_with_admin.post(
            "/admin/database/login",
            data={"username": "admin", "password": "password"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?next=/admin/database"

    def test_sqladmin_logout_redirects_to_birdnetpi_logout(self, client_with_admin):
        """Should redirect GET /admin/database/logout to BirdNET-Pi logout."""
        response = client_with_admin.get("/admin/database/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/logout"

    def test_redirect_routes_take_precedence_over_sqladmin(self, app_with_temp_data):
        """Should verify auth redirect routes are registered and take precedence."""
        # Get all routes from the app
        routes = []
        for route in app_with_temp_data.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append((route.path, route.methods))

        # Check that our redirect routes exist
        assert ("/admin/database/login", {"GET"}) in routes
        assert ("/admin/database/login", {"POST"}) in routes
        assert ("/admin/database/logout", {"GET"}) in routes


class TestSetupRoutes:
    """Test admin setup routes."""

    def test_setup_redirects_when_admin_exists(self, client_with_admin):
        """Should redirect to home when admin already exists."""
        response = client_with_admin.get("/admin/setup", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"


class TestLoginRoutes:
    """Test admin login routes.

    Note: Tests that require full template rendering are covered in integration tests.
    These unit tests focus on redirect behavior and API responses.
    """

    pass  # Login route tests require template rendering - see integration tests


class TestLogoutRoute:
    """Test admin logout route."""

    def test_logout_redirects_to_login(self, client_with_admin):
        """Should redirect to login page after logout."""
        response = client_with_admin.get("/admin/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


class TestAuthStatusAPI:
    """Test authentication status API endpoint."""

    def test_auth_status_unauthenticated(self, client_with_admin):
        """Should return unauthenticated status when not logged in."""
        response = client_with_admin.get("/api/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["username"] is None
