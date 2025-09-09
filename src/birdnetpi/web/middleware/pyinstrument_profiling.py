"""Pyinstrument profiling middleware for FastAPI.

This middleware is only imported when ConfigManager.should_enable_profiling() returns True,
which means pyinstrument is guaranteed to be available.
"""

import logging
from collections.abc import Callable

from pyinstrument import Profiler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class PyInstrumentProfilerMiddleware(BaseHTTPMiddleware):
    """Profile requests using pyinstrument.

    Add ?profile=1 to any request to see profiling output.
    """

    def __init__(self, app: ASGIApp, html_output: bool = True):
        super().__init__(app)
        self.html_output = html_output

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Profile request if ?profile=1 is in query params."""
        # Check if profiling is requested
        profile_param = request.query_params.get("profile")
        if not profile_param or profile_param != "1":
            return await call_next(request)

        # Start profiling
        profiler = Profiler(async_mode="enabled")
        profiler.start()

        try:
            # Process the request
            response = await call_next(request)

            # Stop profiling
            profiler.stop()

            # Generate output
            if self.html_output:
                # Return HTML profiling output
                # Note: pyinstrument 5.1.1 output_html() takes no parameters
                output = profiler.output_html()
                return HTMLResponse(content=output)
            else:
                # Add profiling as text in header (truncated)
                # output_text() also simplified in newer versions
                output = profiler.output_text(unicode=True)
                # Log the full output
                logger.info("Profile for %s %s:\n%s", request.method, request.url.path, output)
                # Add abbreviated version to response header
                lines = output.split("\n")[:5]  # First 5 lines only
                response.headers["X-Profile-Summary"] = " | ".join(lines)
                return response

        except Exception as e:
            logger.error("Profiling error: %s", e)
            # Only stop profiler if it's actually running
            if profiler.is_running:
                profiler.stop()
            # Return error response instead of continuing
            return HTMLResponse(
                content=f"<h1>Profiling Error</h1><pre>{e!s}</pre>", status_code=500
            )
