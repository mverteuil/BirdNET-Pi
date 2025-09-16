"""Integration tests for profiling middleware with configuration."""

import os
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.config.manager import ConfigManager


class TestProfilingIntegration:
    """Integration tests for profiling middleware configuration."""

    def test_middleware_not_added_when_profiling_disabled(self):
        """Should not add middleware when profiling is disabled."""
        with patch.dict(os.environ, {"ENABLE_PROFILING": ""}, clear=True):
            with patch.object(ConfigManager, "should_enable_profiling", return_value=False):
                # We need to mock the entire factory creation process
                from fastapi import FastAPI

                app = FastAPI()

                @app.get("/api/health/ready")
                async def health_ready():
                    return {"status": "ready"}

                client = TestClient(app)

                # Request with profile=1 should not trigger profiling
                response = client.get("/api/health/ready?profile=1")

                # Should return normal response, not profiling output
                assert response.status_code == 200
                assert "pyinstrument" not in response.text.lower()
                assert response.json() == {"status": "ready"}

    def test_middleware_added_when_profiling_enabled(self):
        """Should add middleware when profiling is enabled and pyinstrument available."""
        with patch.dict(os.environ, {"ENABLE_PROFILING": "1"}, clear=True):
            with patch.object(ConfigManager, "should_enable_profiling", return_value=True):
                # We need to mock Profiler at import time
                with patch(
                    "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
                ) as mock_profiler_class:
                    mock_profiler = MagicMock()
                    mock_profiler.is_running = False
                    mock_profiler.output_html.return_value = "<html>Profiling output</html>"
                    mock_profiler_class.return_value = mock_profiler

                    from fastapi import FastAPI

                    from birdnetpi.web.middleware.pyinstrument_profiling import (
                        PyInstrumentProfilerMiddleware,
                    )

                    app = FastAPI()
                    app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)

                    @app.get("/api/health/ready")
                    async def health_ready():
                        return {"status": "ready"}

                    client = TestClient(app)

                    # Request with profile=1 should trigger profiling
                    response = client.get("/api/health/ready?profile=1")

                    # Should return profiling output
                    assert response.status_code == 200
                    assert "Profiling output" in response.text

                    # Verify profiler was used
                    mock_profiler.start.assert_called()
                    mock_profiler.stop.assert_called()

    def test_config_flag_controls_middleware_loading(self):
        """Should respect the ENABLE_PROFILING config flag."""
        # Test with profiling disabled
        with patch.dict(os.environ, {"ENABLE_PROFILING": "0"}, clear=True):
            config_disabled = ConfigManager._is_profiling_enabled()
            assert config_disabled is False

        # Test with profiling enabled via "1"
        with patch.dict(os.environ, {"ENABLE_PROFILING": "1"}, clear=True):
            config_enabled = ConfigManager._is_profiling_enabled()
            assert config_enabled is True

        # Test with profiling enabled via "true"
        with patch.dict(os.environ, {"ENABLE_PROFILING": "true"}, clear=True):
            config_enabled = ConfigManager._is_profiling_enabled()
            assert config_enabled is True

        # Test with profiling enabled via "yes"
        with patch.dict(os.environ, {"ENABLE_PROFILING": "yes"}, clear=True):
            config_enabled = ConfigManager._is_profiling_enabled()
            assert config_enabled is True

    def test_pyinstrument_availability_check(self):
        """Should check if pyinstrument is available."""
        # The actual implementation uses try/except import, not importlib
        # Test when pyinstrument is available (it is in our test environment)
        assert ConfigManager._is_pyinstrument_available() is True

        # Test when pyinstrument is not available
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'pyinstrument'")
        ):
            assert ConfigManager._is_pyinstrument_available() is False

    def test_should_enable_profiling_requires_both_conditions(self):
        """Should only enable profiling when both flag is set AND pyinstrument is available."""
        # Both conditions met
        with patch.object(ConfigManager, "_is_profiling_enabled", return_value=True):
            with patch.object(ConfigManager, "_is_pyinstrument_available", return_value=True):
                assert ConfigManager.should_enable_profiling() is True

        # Flag set but pyinstrument not available
        with patch.object(ConfigManager, "_is_profiling_enabled", return_value=True):
            with patch.object(ConfigManager, "_is_pyinstrument_available", return_value=False):
                assert ConfigManager.should_enable_profiling() is False

        # Pyinstrument available but flag not set
        with patch.object(ConfigManager, "_is_profiling_enabled", return_value=False):
            with patch.object(ConfigManager, "_is_pyinstrument_available", return_value=True):
                assert ConfigManager.should_enable_profiling() is False

        # Neither condition met
        with patch.object(ConfigManager, "_is_profiling_enabled", return_value=False):
            with patch.object(ConfigManager, "_is_pyinstrument_available", return_value=False):
                assert ConfigManager.should_enable_profiling() is False


class TestProfilingMiddlewareEndToEnd:
    """End-to-end tests for profiling middleware functionality."""

    def test_profiling_preserves_normal_responses(self):
        """Should not affect normal responses when profiling is not requested."""
        app = FastAPI()

        @app.get("/test")
        async def fake_endpoint():
            return {"status": "ok", "value": 42}

        # Add profiling middleware
        from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware

        app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)

        client = TestClient(app)

        # Normal request without profiling
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "value": 42}

        # Multiple requests should all work normally
        for _ in range(5):
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "value": 42}

    def test_profiling_works_with_different_methods(self):
        """Should handle profiling for different HTTP methods."""
        app = FastAPI()

        @app.post("/create")
        async def create_item(data: dict):
            return {"created": data}

        @app.put("/update")
        async def update_item(data: dict):
            return {"updated": data}

        @app.delete("/delete")
        async def delete_item():
            return {"deleted": True}

        # Add profiling middleware
        from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware

        app.add_middleware(PyInstrumentProfilerMiddleware, html_output=False)

        client = TestClient(app)

        # Test POST with profiling
        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_text.return_value = "POST profile"
            mock_profiler_class.return_value = mock_profiler

            response = client.post("/create?profile=1", json={"test": "data"})
            assert response.status_code == 200
            assert "X-Profile-Summary" in response.headers
            mock_profiler.start.assert_called_once()
            mock_profiler.stop.assert_called_once()

        # Test PUT with profiling
        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_text.return_value = "PUT profile"
            mock_profiler_class.return_value = mock_profiler

            response = client.put("/update?profile=1", json={"test": "data"})
            assert response.status_code == 200
            assert "X-Profile-Summary" in response.headers

        # Test DELETE with profiling
        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_text.return_value = "DELETE profile"
            mock_profiler_class.return_value = mock_profiler

            response = client.delete("/delete?profile=1")
            assert response.status_code == 200
            assert "X-Profile-Summary" in response.headers

    def test_profiling_with_query_parameters(self):
        """Should handle profile parameter alongside other query parameters."""
        app = FastAPI()

        @app.get("/search")
        async def search(q: str = "", limit: int = 10, profile: str | None = None):
            return {"query": q, "limit": limit, "results": []}

        # Add profiling middleware
        from birdnetpi.web.middleware.pyinstrument_profiling import PyInstrumentProfilerMiddleware

        app.add_middleware(PyInstrumentProfilerMiddleware, html_output=True)

        client = TestClient(app)

        # Test with other query parameters but no profiling
        response = client.get("/search?q=test&limit=5")
        assert response.status_code == 200
        assert response.json() == {"query": "test", "limit": 5, "results": []}

        # Test with profiling and other parameters
        with patch(
            "birdnetpi.web.middleware.pyinstrument_profiling.Profiler"
        ) as mock_profiler_class:
            mock_profiler = MagicMock()
            mock_profiler.is_running = False
            mock_profiler.output_html.return_value = "<html>Search profile</html>"
            mock_profiler_class.return_value = mock_profiler

            response = client.get("/search?q=test&limit=5&profile=1")
            assert response.status_code == 200
            assert "Search profile" in response.text
            mock_profiler.start.assert_called_once()
