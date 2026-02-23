"""Tests for authentication utilities."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from starlette.authentication import AuthCredentials, SimpleUser
from starlette.datastructures import URL
from starlette.requests import HTTPConnection, Request
from starlette.responses import RedirectResponse

from birdnetpi.utils.auth import (
    AdminUser,
    AuthService,
    SessionAuthBackend,
    pwd_context,
    require_admin_relative,
)


class TestPwdContext:
    """Test password hashing context."""

    def test_hash_and_verify(self):
        """Should hash password and verify correctly."""
        password = "test_password_123"
        hashed = pwd_context.hash(password)

        # Hash should be different from original
        assert hashed != password

        # Should verify correctly
        assert pwd_context.verify(password, hashed)

        # Wrong password should not verify
        assert not pwd_context.verify("wrong_password", hashed)


class TestAdminUser:
    """Test AdminUser model."""

    def test_create_admin_user(self):
        """Should create AdminUser with required fields."""
        now = datetime.now()
        user = AdminUser(
            username="admin",
            password_hash="$argon2id$test_hash",
            created_at=now,
        )

        assert user.username == "admin"
        assert user.password_hash == "$argon2id$test_hash"
        assert user.created_at == now


class TestAuthService:
    """Test AuthService class."""

    @pytest.fixture
    def auth_service(self, path_resolver):
        """Create AuthService with test path resolver."""
        return AuthService(path_resolver)

    def test_admin_file_path(self, auth_service, path_resolver):
        """Should set admin file path from path resolver."""
        expected_path = path_resolver.get_data_dir() / "admin_user.json"
        assert auth_service.admin_file == expected_path

    def test_admin_exists_false_when_file_missing(self, auth_service):
        """Should return False when admin file doesn't exist."""
        assert not auth_service.admin_exists()

    def test_admin_exists_true_when_file_exists(self, auth_service, path_resolver):
        """Should return True when admin file exists."""
        # Create admin file
        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        admin_file.parent.mkdir(parents=True, exist_ok=True)
        admin_file.write_text("{}")

        assert auth_service.admin_exists()

    def test_load_admin_user_returns_none_when_file_missing(self, auth_service):
        """Should return None when admin file doesn't exist."""
        assert auth_service.load_admin_user() is None

    def test_load_admin_user_returns_none_on_invalid_json(self, auth_service, path_resolver):
        """Should return None when admin file contains invalid JSON."""
        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        admin_file.parent.mkdir(parents=True, exist_ok=True)
        admin_file.write_text("not valid json")

        assert auth_service.load_admin_user() is None

    def test_load_admin_user_returns_none_on_invalid_schema(self, auth_service, path_resolver):
        """Should return None when admin file has invalid schema."""
        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        admin_file.parent.mkdir(parents=True, exist_ok=True)
        admin_file.write_text('{"invalid": "schema"}')

        assert auth_service.load_admin_user() is None

    def test_load_admin_user_success(self, auth_service, path_resolver):
        """Should load admin user from valid JSON file."""
        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        admin_file.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        admin_data = {
            "username": "testadmin",
            "password_hash": "$argon2id$test_hash",
            "created_at": now.isoformat(),
        }
        admin_file.write_text(json.dumps(admin_data))

        user = auth_service.load_admin_user()

        assert user is not None
        assert user.username == "testadmin"
        assert user.password_hash == "$argon2id$test_hash"

    def test_save_admin_user(self, auth_service, path_resolver):
        """Should save admin user with hashed password."""
        auth_service.save_admin_user("newadmin", "secure_password")

        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        assert admin_file.exists()

        # Load and verify
        with open(admin_file) as f:
            data = json.load(f)

        assert data["username"] == "newadmin"
        # Password should be hashed, not plain text
        assert data["password_hash"] != "secure_password"
        assert data["password_hash"].startswith("$argon2")
        assert "created_at" in data

    def test_save_admin_user_sets_permissions(self, auth_service, path_resolver):
        """Should set file permissions to 0600."""
        auth_service.save_admin_user("admin", "password")

        admin_file = path_resolver.get_data_dir() / "admin_user.json"
        # Get file mode (last 3 octal digits)
        mode = admin_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_verify_password_success(self, auth_service):
        """Should return True for correct password."""
        password = "correct_password"
        password_hash = pwd_context.hash(password)

        assert auth_service.verify_password(password, password_hash)

    def test_verify_password_failure(self, auth_service):
        """Should return False for incorrect password."""
        password_hash = pwd_context.hash("correct_password")

        assert not auth_service.verify_password("wrong_password", password_hash)


class TestRequireAdminRelative:
    """Test require_admin_relative decorator."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request with auth."""
        request = create_autospec(Request, instance=True)
        request.auth = MagicMock(spec=AuthCredentials)
        request.url = create_autospec(URL, instance=True)
        request.url.path = "/admin/settings"
        request.url.query = ""
        return request

    @pytest.mark.asyncio
    async def test_allows_authenticated_request(self, mock_request):
        """Should allow request when user is authenticated."""
        mock_request.auth.scopes = ["authenticated"]

        @require_admin_relative()
        async def protected_route(request):
            return {"status": "ok"}

        result = await protected_route(mock_request)
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_redirects_unauthenticated_request(self, mock_request):
        """Should redirect to login when user is not authenticated."""
        mock_request.auth.scopes = []

        @require_admin_relative()
        async def protected_route(request):
            return {"status": "ok"}

        result = await protected_route(mock_request)

        # Should be a redirect response
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "/admin/login" in result.headers["location"]
        assert "next=%2Fadmin%2Fsettings" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_preserves_query_string_in_redirect(self, mock_request):
        """Should preserve query string when redirecting."""
        mock_request.auth.scopes = []
        mock_request.url.query = "tab=general"

        @require_admin_relative()
        async def protected_route(request):
            return {"status": "ok"}

        result = await protected_route(mock_request)

        # Should include query string in next parameter
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        location = result.headers["location"]
        assert "next=" in location
        # URL-encoded version of "/admin/settings?tab=general"
        assert "%2Fadmin%2Fsettings%3Ftab%3Dgeneral" in location

    @pytest.mark.asyncio
    async def test_custom_redirect_path(self, mock_request):
        """Should use custom redirect path when specified."""
        mock_request.auth.scopes = []

        @require_admin_relative(redirect_path="/custom/login")
        async def protected_route(request):
            return {"status": "ok"}

        result = await protected_route(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert result.headers["location"].startswith("/custom/login")


class TestSessionAuthBackend:
    """Test SessionAuthBackend class."""

    @pytest.fixture
    def auth_backend(self):
        """Create SessionAuthBackend instance."""
        return SessionAuthBackend()

    @pytest.mark.asyncio
    async def test_authenticate_returns_none_without_session(self, auth_backend):
        """Should return None when no username in session."""
        conn = create_autospec(HTTPConnection, instance=True)
        conn.session = {}

        with patch("birdnetpi.utils.auth.load_session", new_callable=AsyncMock) as mock_load:
            result = await auth_backend.authenticate(conn)

        mock_load.assert_called_once_with(conn)
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_returns_credentials_with_session(self, auth_backend):
        """Should return credentials when username in session."""
        conn = create_autospec(HTTPConnection, instance=True)
        conn.session = {"username": "testuser"}

        with patch("birdnetpi.utils.auth.load_session", new_callable=AsyncMock) as mock_load:
            result = await auth_backend.authenticate(conn)

        mock_load.assert_called_once_with(conn)
        assert result is not None

        credentials, user = result
        assert isinstance(credentials, AuthCredentials)
        assert "authenticated" in credentials.scopes
        assert isinstance(user, SimpleUser)
        assert user.username == "testuser"
