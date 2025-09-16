"""Tests for PyInstrument profiling middleware."""

import asyncio
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware


@pytest.fixture
def app():
    """Create a FastAPI app with the profiling middleware."""
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"message": "Hello World"}

    @app.get("/slow")
    async def slow_endpoint():
        await asyncio.sleep(0.1)
        return {"message": "Slow response"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    return app


@pytest.fixture
def app_with_html_profiling(app):
    """Add HTML profiling middleware to the app."""
    app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)
    return app


@pytest.fixture
def app_with_text_profiling(app):
    """Add text profiling middleware to the app."""
    app.add_middleware(PyInstrumentProfilerMiddleware, html_output=False)
    return app


class TestProfilingMiddleware:
    """Test the PyInstrumentProfilerMiddleware."""

    def test_no_profiling_without_parameter(self, app_with_html_profiling):
        """Should not profile when profile parameter is not set."""
        client = TestClient(app_with_html_profiling)
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}
        assert "pyinstrument" not in response.text.lower()

    def test_no_profiling_with_wrong_parameter(self, app_with_html_profiling):
        """Should not profile when profile parameter is not '1'."""
        client = TestClient(app_with_html_profiling)

        # Test with profile=0
        response = client.get("/?profile=0")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

        # Test with profile=true
        response = client.get("/?profile=true")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

        # Test with profile=yes
        response = client.get("/?profile=yes")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    def test_html_profiling_enabled(self, mock_profiler_class, app_with_html_profiling):
        """Should return HTML profiling output when profile=1."""
        # Setup mock profiler
        mock_profiler = MagicMock()
        mock_profiler.is_running = False
        mock_profiler.output_html.return_value = "<html><body>Profiling Results</body></html>"
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_html_profiling)
        response = client.get("/?profile=1")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Profiling Results" in response.text

        # Verify profiler was used correctly
        mock_profiler_class.assert_called_once_with(async_mode="enabled")
        mock_profiler.start.assert_called_once()
        mock_profiler.stop.assert_called_once()
        mock_profiler.output_html.assert_called_once()

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    def test_text_profiling_enabled(self, mock_profiler_class, app_with_text_profiling):
        """Should add profiling to headers when html_output=False."""
        # Setup mock profiler
        mock_profiler = MagicMock()
        mock_profiler.is_running = False
        mock_profiler.output_text.return_value = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6"
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_text_profiling)
        response = client.get("/?profile=1")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}
        assert "X-Profile-Summary" in response.headers
        # Should only include first 5 lines
        assert response.headers["X-Profile-Summary"] == "Line 1 | Line 2 | Line 3 | Line 4 | Line 5"

        # Verify profiler was used correctly
        mock_profiler.start.assert_called_once()
        mock_profiler.stop.assert_called_once()
        mock_profiler.output_text.assert_called_once_with(unicode=True)

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    @patch("birdnetpi.web.middleware.pyinstrument_profiling.logger")
    def test_text_profiling_logs_output(
        self, mock_logger, mock_profiler_class, app_with_text_profiling
    ):
        """Should log full profiling output when html_output=False."""
        # Setup mock profiler
        mock_profiler = MagicMock()
        mock_profiler.is_running = False
        mock_profiler.output_text.return_value = "Full profiling output"
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_text_profiling)
        response = client.get("/?profile=1")

        assert response.status_code == 200
        # Verify logging was called
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[0]
        assert "Profile for" in args[0]
        assert "GET" in args[1]
        assert "/" in args[2]
        assert "Full profiling output" in args[3]

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    @patch("birdnetpi.web.middleware.pyinstrument_profiling.logger")
    def test_profiling_error_handling(
        self, mock_logger, mock_profiler_class, app_with_html_profiling
    ):
        """Should handle errors during profiling gracefully."""
        # Setup mock profiler that raises an error after starting
        mock_profiler = MagicMock()
        # Configure is_running as a property that returns True initially
        type(mock_profiler).is_running = PropertyMock(side_effect=[False, True, True])
        # First call to start succeeds, then stop raises an error
        mock_profiler.start.return_value = None
        mock_profiler.stop.side_effect = Exception("Profiling failed")
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_html_profiling)
        response = client.get("/?profile=1")

        assert response.status_code == 500
        assert "Profiling Error" in response.text
        assert "Profiling failed" in response.text

        # Verify error was logged
        mock_logger.error.assert_called_once()
        assert "Profiling error" in mock_logger.error.call_args[0][0]

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    def test_profiling_with_slow_endpoint(self, mock_profiler_class, app_with_html_profiling):
        """Should profile slow endpoints correctly."""
        # Setup mock profiler
        mock_profiler = MagicMock()
        mock_profiler.is_running = False
        mock_profiler.output_html.return_value = "<html>Slow endpoint profile</html>"
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_html_profiling)
        response = client.get("/slow?profile=1")

        assert response.status_code == 200
        assert "Slow endpoint profile" in response.text

        # Profiler should have been started and stopped
        mock_profiler.start.assert_called_once()
        mock_profiler.stop.assert_called_once()

    def test_profiling_preserves_exception(self, app_with_html_profiling):
        """Should not interfere with normal exception handling when not profiling."""
        client = TestClient(app_with_html_profiling, raise_server_exceptions=False)

        # Without profiling, exceptions should propagate normally
        response = client.get("/error")
        assert response.status_code == 500
        # The middleware doesn't interfere - the error is properly handled
        # The exact error message depends on FastAPI's error handling configuration
        assert "Internal Server Error" in response.text

    @patch("birdnetpi.web.middleware.pyinstrument_profiling.Profiler")
    @patch("birdnetpi.web.middleware.pyinstrument_profiling.logger")
    def test_profiler_not_running_on_error(
        self, mock_logger, mock_profiler_class, app_with_html_profiling
    ):
        """Should handle case where profiler is not running during error."""
        # Setup mock profiler that fails and is_running returns False
        mock_profiler = MagicMock()
        mock_profiler.is_running = False
        # Simulate error during processing after profiler has stopped
        mock_profiler.output_html.side_effect = Exception("Output failed")
        mock_profiler_class.return_value = mock_profiler

        client = TestClient(app_with_html_profiling)
        response = client.get("/?profile=1")

        assert response.status_code == 500
        assert "Profiling Error" in response.text

        # stop() should not be called again when profiler is not running
        # (it was called once during normal flow, but not in error handler)
        assert mock_profiler.stop.call_count == 1


class TestMiddlewareDispatch:
    """Test the dispatch method directly."""

    @pytest.mark.asyncio
    async def test_dispatch_without_profiling(self):
        """Should pass through when profile parameter is not set."""
        middleware = PyInstrumentProfilerMiddleware(app=MagicMock())

        # Create mock request without profile parameter
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {}

        # Create mock call_next that returns a response
        mock_response = Response(content="Normal response")

        async def mock_call_next(request):
            return mock_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert result == mock_response
        assert result.body == b"Normal response"

    @pytest.mark.asyncio
    async def test_dispatch_with_html_profiling(self):
        """Should return HTML profiling output."""
        middleware = PyInstrumentProfilerMiddleware(app=MagicMock(), html_output=True)

        # Create mock request with profile=1
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"profile": "1"}
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        # Create mock call_next
        mock_response = Response(content="Normal response")

        async def mock_call_next(request):
            return mock_response

        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_html.return_value = "<html>Profile</html>"
            mock_profiler_class.return_value = mock_profiler

            result = await middleware.dispatch(mock_request, mock_call_next)

            assert isinstance(result, HTMLResponse)
            assert b"Profile" in result.body

    @pytest.mark.asyncio
    async def test_dispatch_with_text_profiling(self):
        """Should add profiling to headers with text output."""
        middleware = PyInstrumentProfilerMiddleware(app=MagicMock(), html_output=False)

        # Create mock request with profile=1
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"profile": "1"}
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        # Create mock call_next that returns a proper Response
        async def mock_call_next(request):
            return Response(content="Normal response")

        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_text.return_value = "Profile line 1\nProfile line 2"
            mock_profiler_class.return_value = mock_profiler

            result = await middleware.dispatch(mock_request, mock_call_next)

            assert "X-Profile-Summary" in result.headers
            assert "Profile line 1 | Profile line 2" in result.headers["X-Profile-Summary"]
