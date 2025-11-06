"""Setup redirect middleware for BirdNET-Pi.

Redirects all requests to the setup wizard if no admin user exists.
"""

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response


class SetupRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect to setup wizard if no admin user exists.

    This middleware checks if an admin user has been created. If not,
    it redirects all requests to /admin/setup except for:
    - The setup page itself
    - The login page
    - Static files
    - Health check endpoints
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and redirect to setup if needed.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/endpoint in chain

        Returns:
            Response from next handler or redirect to setup
        """
        # Paths that should not trigger setup redirect
        exempt_paths = [
            "/admin/setup",
            "/admin/login",
            "/static/",
            "/api/health",
        ]

        # Allow exempt paths through
        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await call_next(request)

        # Check if admin user exists
        auth_service = request.app.state.container.auth_service()
        if not auth_service.admin_exists():
            return RedirectResponse(url="/admin/setup", status_code=303)

        # Admin exists, continue normally
        return await call_next(request)
