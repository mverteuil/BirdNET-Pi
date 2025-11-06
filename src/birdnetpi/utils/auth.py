"""Authentication utilities for BirdNET-Pi admin interface.

Provides session-based authentication using Starlette's built-in
authentication system with Redis-backed sessions.
"""

from datetime import datetime

from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
    requires,
)
from starlette.requests import HTTPConnection

from birdnetpi.system.path_resolver import PathResolver

# Password hashing context using Argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Syntactic sugar for common authentication requirement
# Usage: @require_admin decorator on admin view routes
require_admin = requires("authenticated", redirect="/admin/login")


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

        Called by AuthenticationMiddleware on every request. Session is
        automatically available via SessionMiddleware (lazy-loaded on first access).

        Args:
            conn: HTTP connection (request or WebSocket)

        Returns:
            Tuple of (AuthCredentials, SimpleUser) if authenticated,
            None if not authenticated
        """
        # Session is automatically available from SessionMiddleware
        # No need to call load_session() - it's lazy-loaded on first access
        username = conn.session.get("username")
        if not username:
            return None  # Not authenticated

        # Return authenticated user with "authenticated" scope
        # The scope is used by @requires decorator for authorization
        return AuthCredentials(["authenticated"]), SimpleUser(username)
