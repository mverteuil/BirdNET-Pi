"""Middleware to inject update status into all template contexts."""

import logging
from typing import TYPE_CHECKING, Any

from dependency_injector.wiring import Provide, inject
from fastapi import Request
from jinja2 import Environment
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class UpdateBannerMiddleware(BaseHTTPMiddleware):
    """Middleware that checks for update status and adds it to template context.

    This middleware:
    1. Checks the cache for update status on each request
    2. Makes the update_status available to all templates via request state
    3. Allows the update banner to appear on all pages when updates are available
    """

    @inject
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        cache: Cache = Provide[Container.cache_service],
    ) -> Response:
        """Process the request and add update status to request state.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain
            cache: The cache service for checking update status

        Returns:
            The response from the next handler
        """
        try:
            # Check cache for update status
            update_status = cache.get("update:status")

            # Add to request state so templates can access it
            request.state.update_status = update_status

        except Exception as e:
            # Log error but don't fail the request
            logger.debug(f"Failed to get update status: {e}")
            request.state.update_status = None

        # Process the request
        response = await call_next(request)
        return response


def add_update_status_to_templates(
    templates: Jinja2Templates | Environment, container: Container
) -> None:
    """Add a template context processor that includes update_status.

    This function adds a global context processor to Jinja2 templates
    that makes update_status available to all templates automatically.

    Args:
        templates: The Jinja2Templates instance
        container: The dependency injection container
    """
    # Get services from container
    cache = container.cache_service()
    config = container.config()

    def get_update_status() -> dict[str, Any] | None:
        """Get current update status from cache if banner is enabled."""
        try:
            # Only check for updates if banner is enabled
            if not config.updates.show_banner:
                return None
            return cache.get("update:status")
        except Exception:
            return None

    # Get the globals dict from either Jinja2Templates or Environment
    if isinstance(templates, Jinja2Templates):
        # Starlette Jinja2Templates
        globals_dict = templates.env.globals  # type: ignore[attr-defined]
    else:
        # Plain Jinja2 Environment
        globals_dict = templates.globals

    # Add as a template global function
    globals_dict["get_update_status"] = get_update_status

    # Also add a filter to check if updates are available
    def update_available() -> bool:
        """Check if an update is available and banner is enabled."""
        if not config.updates.show_banner:
            return False
        status = get_update_status()
        return bool(status and status.get("available"))

    globals_dict["update_available"] = update_available

    # Add function to check if development warning should show
    def show_development_warning() -> bool:
        """Check if development warning should be shown."""
        if not config.updates.show_development_warning:
            return False
        status = get_update_status()
        return bool(status and status.get("version_type") == "development")

    globals_dict["show_development_warning"] = show_development_warning
