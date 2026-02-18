"""Authentication utilities for BirdNET-Pi admin interface.

Provides session-based authentication using Starlette's built-in
authentication system with Redis-backed sessions.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime

from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection
from starlette.responses import RedirectResponse
from starsessions import load_session

from birdnetpi.system.path_resolver import PathResolver

# Password hashing context using Argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def require_admin_relative(
    redirect_path: str = "/admin/login",
) -> Callable[[Callable[..., Awaitable[object]]], Callable[..., Awaitable[object]]]:
    """Create authentication decorator that uses relative URLs for redirects.

    Unlike Starlette's @requires which generates absolute URLs, this decorator
    uses relative paths to avoid issues with proxies and URL parsing.

    Args:
        redirect_path: Relative path to redirect to if not authenticated

    Returns:
        Decorator function that wraps route handlers
    """
    from functools import wraps
    from urllib.parse import urlencode

    def decorator(
        func: Callable[..., Awaitable[object]],
    ) -> Callable[..., Awaitable[object]]:
        @wraps(func)
        async def wrapper(request: HTTPConnection, *args: object, **kwargs: object) -> object:
            # Check if user has required authentication scope
            # This uses request.auth which works with or without AuthenticationMiddleware
            if "authenticated" not in request.auth.scopes:
                # Build relative redirect URL with next parameter
                next_qparam = urlencode({"next": str(request.url.path)})
                if request.url.query:
                    next_qparam = urlencode({"next": f"{request.url.path}?{request.url.query}"})

                redirect_url = f"{redirect_path}?{next_qparam}"
                return RedirectResponse(url=redirect_url, status_code=303)

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


# Syntactic sugar for common authentication requirement
# Usage: @require_admin decorator on admin view routes
require_admin = require_admin_relative()


class AdminUser(BaseModel):
    """Admin user model for file-based storage."""

    username: str
    password_hash: str
    created_at: datetime


class AuthService:
    """Handles admin user file operations and password hashing.

    Stores a single admin user in a JSON file with permissions set to 0600.
    """

    def __init__(self, path_resolver: PathResolver) -> None:
        """Initialize auth service.

        Args:
            path_resolver: PathResolver instance for determining file paths
        """
        self.admin_file = path_resolver.get_data_dir() / "admin_user.json"

    def load_admin_user(self) -> AdminUser | None:
        """Load admin user from JSON file.

        Returns:
            AdminUser if file exists and is valid, None otherwise
        """
        if not self.admin_file.exists():
            return None

        import json

        try:
            with open(self.admin_file) as f:
                data = json.load(f)
            return AdminUser(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    def save_admin_user(self, username: str, password: str) -> None:
        """Hash password and save to JSON with 0600 permissions.

        Args:
            username: Admin username
            password: Plain text password (will be hashed)
        """
        import json

        admin = AdminUser(
            username=username, password_hash=pwd_context.hash(password), created_at=datetime.now()
        )

        # Write to file
        with open(self.admin_file, "w") as f:
            json.dump(admin.model_dump(), f, default=str, indent=2)

        # Set restrictive permissions (owner read/write only)
        self.admin_file.chmod(0o600)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash.

        Args:
            password: Plain text password to verify
            password_hash: Argon2 hash to verify against

        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(password, password_hash)

    def admin_exists(self) -> bool:
        """Check if admin user file exists.

        Returns:
            True if admin_user.json exists, False otherwise
        """
        return self.admin_file.exists()


class SessionAuthBackend(AuthenticationBackend):
    """Session-based authentication backend for Starlette.

    Checks for username in session and returns appropriate credentials.
    """

    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, SimpleUser] | None:
        """Authenticate request based on session data.

        Called by AuthenticationMiddleware on every request. Explicitly loads
        session from starsessions middleware before accessing it.

        Args:
            conn: HTTP connection (request or WebSocket)

        Returns:
            Tuple of (AuthCredentials, SimpleUser) if authenticated,
            None if not authenticated
        """
        # Load session from starsessions middleware
        await load_session(conn)

        # Get username from session
        username = conn.session.get("username")
        if not username:
            return None  # Not authenticated

        # Return authenticated user with "authenticated" scope
        # The scope is used by @requires decorator for authorization
        return AuthCredentials(["authenticated"]), SimpleUser(username)
