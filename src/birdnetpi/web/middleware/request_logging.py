"""Structured request logging middleware for FastAPI."""

import logging
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Get logger - will be wrapped by structlog
logger = logging.getLogger(__name__)


class StructuredRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests in structured format."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request details in structured format."""
        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Build extra fields dict, excluding None values for cleaner logs
        extra_fields = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        # Add optional fields if present
        if request.url.query:
            extra_fields["query"] = str(request.url.query)
        if request.client:
            extra_fields["client_host"] = request.client.host
            extra_fields["client_port"] = request.client.port
        if user_agent := request.headers.get("user-agent"):
            extra_fields["user_agent"] = user_agent

        # Log request details in structured format
        logger.info(
            f"{request.method} {request.url.path} {response.status_code}", extra=extra_fields
        )

        return response
