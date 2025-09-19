"""Tests for log API routes."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.system.log_reader import LogReaderService
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS


@pytest.fixture
def mock_log_reader():
    """Create a mock LogReaderService.

    This fixture creates the mock and handles cleanup.
    """
    mock = AsyncMock(spec=LogReaderService)
    yield mock
    # No cleanup needed - mock is garbage collected


@pytest.fixture
async def app_with_mock_log_reader(path_resolver, mock_log_reader):
    """Create FastAPI app with mocked log reader service.

    This fixture overrides the log reader BEFORE creating the app,
    ensuring the mock is properly wired.
    """
    from dependency_injector import providers

    from birdnetpi.config import ConfigManager
    from birdnetpi.database.core import CoreDatabaseService
    from birdnetpi.web.core.factory import create_app

    # Override Container providers BEFORE creating app
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.database_path.override(providers.Factory(lambda: path_resolver.get_database_path()))

    # Create config
    manager = ConfigManager(path_resolver)
    test_config = manager.load()
    Container.config.override(providers.Singleton(lambda: test_config))

    # Create database service
    temp_db_service = CoreDatabaseService(path_resolver.get_database_path())
    await temp_db_service.initialize()
    Container.core_database.override(providers.Singleton(lambda: temp_db_service))

    # Override log reader with our mock
    Container.log_reader.override(providers.Object(mock_log_reader))

    # NOW create the app with all overrides in place
    app = create_app()
    app._test_db_service = temp_db_service  # type: ignore[attr-defined]

    yield app

    # Cleanup
    if hasattr(temp_db_service, "async_engine") and temp_db_service.async_engine:
        await temp_db_service.async_engine.dispose()

    # Reset overrides
    Container.path_resolver.reset_override()
    Container.database_path.reset_override()
    Container.config.reset_override()
    Container.core_database.reset_override()
    Container.log_reader.reset_override()


class TestLogsAPIRoutes:
    """Test log API routes."""

    def test_get_logs(self, app_with_mock_log_reader, mock_log_reader):
        """Should return historical logs with correct format and metadata."""
        # Configure the mock
        mock_log_reader.get_logs.return_value = [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "service": "fastapi",
                "level": "INFO",
                "message": "Test log 1",
                "extra": {},
            },
            {
                "timestamp": "2024-01-15T10:31:00Z",
                "service": "audio_capture",
                "level": "ERROR",
                "message": "Test error",
                "extra": {"error_code": 500},
            },
        ]

        # Override container before creating TestClient
        Container.log_reader.override(providers.Object(mock_log_reader))

        try:
            with TestClient(app_with_mock_log_reader) as client:
                response = client.get("/api/logs")
        finally:
            Container.log_reader.reset_override()

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) == 2
        assert data["logs"][0]["service"] == "fastapi"
        assert data["logs"][1]["level"] == "ERROR"
        assert data["total"] == 2
        assert "levels" in data

    def test_get_logs_with_time_filter(self, app_with_mock_log_reader, mock_log_reader):
        """Should apply time filters when fetching logs."""
        # Configure the mock
        mock_log_reader.get_logs.return_value = [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "service": "fastapi",
                "level": "ERROR",
                "message": "Filtered log",
                "extra": {},
            }
        ]

        with TestClient(app_with_mock_log_reader) as client:
            response = client.get(
                "/api/logs",
                params={
                    "start_time": "2024-01-15T00:00:00Z",
                    "end_time": "2024-01-16T00:00:00Z",
                    "limit": 10,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1

        # Verify the mock was called with correct parameters
        mock_log_reader.get_logs.assert_called_once()
        call_args = mock_log_reader.get_logs.call_args[1]
        assert call_args["services"] is None  # No service filtering
        assert call_args["level"] is None  # No level filtering
        assert call_args["keyword"] is None  # No keyword filtering

    def test_get_logs_error_handling(self, app_with_mock_log_reader, mock_log_reader):
        """Should handle errors gracefully and return empty list with error message."""
        # Configure the mock to raise an error
        mock_log_reader.get_logs.side_effect = Exception("Database error")

        with TestClient(app_with_mock_log_reader) as client:
            response = client.get("/api/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == []
        assert data["total"] == 0
        assert "error" in data
        assert "Database error" in data["error"]

    def test_stream_logs(self, app_with_mock_log_reader, mock_log_reader):
        """Should stream logs via SSE with correct event format."""

        # Create an async generator for streaming
        async def mock_stream():
            yield {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "test",
                "level": "INFO",
                "message": "Stream log 1",
            }
            yield {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "test",
                "level": "ERROR",
                "message": "Stream log 2",
            }

        mock_log_reader.stream_logs.return_value = mock_stream()

        with TestClient(app_with_mock_log_reader) as client:
            # SSE endpoints return a streaming response
            # TestClient handles streaming automatically
            response = client.get("/api/logs/stream")
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

            # For TestClient, we can read the entire response
            # The response will contain all SSE events
            content = response.text
            lines = content.strip().split("\n")

            # Check that we have SSE formatted events
            events = []
            for line in lines:
                if line.startswith("data: "):
                    events.append(line)

            # Should have connection event and log events
            assert len(events) >= 1
            assert "connected" in events[0]

    def test_stream_logs_no_filters(self, app_with_mock_log_reader, mock_log_reader):
        """Should stream all logs without server-side filtering."""

        async def mock_stream():
            yield {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "filtered_service",
                "level": "WARNING",
                "message": "Filtered stream",
            }

        mock_log_reader.stream_logs.return_value = mock_stream()

        with TestClient(app_with_mock_log_reader) as client:
            # No parameters passed - filtering is client-side
            response = client.get("/api/logs/stream")
            assert response.status_code == 200

            # Verify the mock was called without filters
            mock_log_reader.stream_logs.assert_called_once()
            call_args = mock_log_reader.stream_logs.call_args[1]
            assert call_args["services"] is None
            assert call_args["level"] is None
            assert call_args["keyword"] is None

    def test_get_log_levels(self, app_with_mock_log_reader):
        """Should return all log levels with correct structure and colors."""
        with TestClient(app_with_mock_log_reader) as client:
            response = client.get("/api/logs/levels")

        assert response.status_code == 200
        levels = response.json()
        assert len(levels) == len(LOG_LEVELS)

        # Check structure of level info
        for level in levels:
            assert "name" in level
            assert "value" in level
            assert "color" in level
            assert "aria_label" in level

        # Check specific levels
        debug_level = next(lev for lev in levels if lev["name"] == "DEBUG")
        assert debug_level["value"] == 10
        assert debug_level["color"] == "#6c757d"

    def test_log_entry_parsing_edge_cases(self, app_with_mock_log_reader, mock_log_reader):
        """Should handle malformed log entries gracefully."""
        # Return logs with various edge cases
        mock_log_reader.get_logs.return_value = [
            # Valid log with string timestamp
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "service": "test",
                "level": "INFO",
                "message": "Normal log",
            },
            # Malformed log (will be caught in try/except)
            "not a dict",
            # Log with missing fields
            {
                "service": "broken",
            },
        ]

        with TestClient(app_with_mock_log_reader) as client:
            response = client.get("/api/logs")

        assert response.status_code == 200
        data = response.json()

        # Should handle the valid log
        assert len(data["logs"]) >= 1
        assert data["logs"][0]["message"] == "Normal log"

    def test_limit_parameter(self, app_with_mock_log_reader, mock_log_reader):
        """Should respect limit parameter."""
        # Create 20 mock logs
        mock_logs = [
            {
                "timestamp": f"2024-01-15T10:{i:02d}:00Z",
                "service": "test",
                "level": "INFO",
                "message": f"Log {i}",
            }
            for i in range(20)
        ]

        mock_log_reader.get_logs.return_value = mock_logs[:5]  # Return only 5 logs

        with TestClient(app_with_mock_log_reader) as client:
            response = client.get("/api/logs", params={"limit": 5})

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert len(data["logs"]) == 5
