"""Internationalization middleware for FastAPI."""

from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class LanguageMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically set language based on request headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and install appropriate translation."""
        # Install translation for this request
        translation_manager = request.app.state.translation_manager
        translation_manager.install_for_request(request)

        # Continue processing
        response = await call_next(request)
        return response
