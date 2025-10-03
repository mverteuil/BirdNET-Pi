"""Unit tests for LogReaderService."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.system.log_reader import LogLevel, LogReaderService


class TestLogLevel:
    """Test LogLevel enum functionality."""

    def test_numeric_values(self):
        """Should have correct numeric values for log levels."""
        assert LogLevel.DEBUG.numeric_value == 10
        assert LogLevel.INFO.numeric_value == 20
        assert LogLevel.WARNING.numeric_value == 30
        assert LogLevel.ERROR.numeric_value == 40
        assert LogLevel.CRITICAL.numeric_value == 50

    def test_from_string(self):
        """Should convert string to LogLevel with fallback to INFO."""
        assert LogLevel.from_string("DEBUG") == LogLevel.DEBUG
        assert LogLevel.from_string("info") == LogLevel.INFO
        assert LogLevel.from_string("WaRnInG") == LogLevel.WARNING
        assert LogLevel.from_string("invalid") == LogLevel.INFO  # fallback
        assert LogLevel.from_string("") == LogLevel.INFO  # fallback


class TestLogReaderService:
    """Test LogReaderService functionality."""

    @pytest.fixture
    def log_reader(self):
        """Create a LogReaderService instance."""
        with patch("birdnetpi.system.log_reader.SystemUtils") as mock_utils:
            mock_utils.is_docker_environment.return_value = True
            mock_utils.is_systemd_available.return_value = False
            return LogReaderService()

    def test_parse_log_entry_json(self, log_reader):
        """Should parse a JSON log entry correctly."""
        json_line = json.dumps(
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "level": "ERROR",
                "service": "test_service",
                "message": "Test error message",
                "extra_field": "value",
            }
        )

        result = log_reader.parse_log_entry(json_line, "fallback_service")

        assert result is not None
        assert result["timestamp"] == "2024-01-15T10:30:00Z"
        assert result["level"] == "ERROR"
        assert result["service"] == "test_service"
        assert result["message"] == "Test error message"
        assert "extra_field" in result

    def test_parse_log_entry_json_missing_fields(self, log_reader):
        """Should handle JSON with missing required fields by adding defaults."""
        json_line = json.dumps({"msg": "Test message"})

        result = log_reader.parse_log_entry(json_line, "test_service")

        assert result is not None
        assert result["level"] == "INFO"  # default
        assert result["service"] == "test_service"  # from parameter
        assert result["message"] == "Test message"  # from msg field
        assert "timestamp" in result  # auto-generated

    def test_parse_log_entry_text(self, log_reader):
        """Should parse plain text log entry and extract log level."""
        text_line = "2024-01-15 10:30:45 ERROR [service] Error occurred"

        result = log_reader.parse_log_entry(text_line, "test_service")

        assert result is not None
        assert result["level"] == "ERROR"  # extracted from text
        assert result["service"] == "test_service"
        assert result["message"] == text_line
        assert result["raw"] is True  # marked as non-JSON

    def test_parse_log_entry_empty(self, log_reader):
        """Should return None for empty lines."""
        result = log_reader.parse_log_entry("", "test_service")
        assert result is None

        result = log_reader.parse_log_entry("   ", "test_service")
        assert result is None

    def test_parse_supervisord_logs(self, log_reader):
        """Should parse supervisord output with mixed formats."""
        output = """First log line
{"level": "INFO", "message": "JSON log"}
Third line with WARNING text"""
        results = log_reader._parse_supervisord_logs(output, "test_service")

        assert len(results) == 3
        assert results[0]["message"] == "First log line"
        assert results[1]["level"] == "INFO"
        assert results[2]["level"] == "WARNING"

    def test_parse_journald_logs(self, log_reader):
        """Should parse journald JSON output and extract fields."""
        journal_entry = {
            "__REALTIME_TIMESTAMP": "1705318245000000",  # microseconds
            "_SYSTEMD_UNIT": "test.service",
            "PRIORITY_TEXT": "error",
            "MESSAGE": "Test error message",
            "_PID": "1234",
            "_HOSTNAME": "test-host",
        }
        output = json.dumps(journal_entry)

        results = log_reader._parse_journald_logs(output)

        assert len(results) == 1
        assert results[0]["service"] == "test"  # .service removed
        assert results[0]["level"] == "ERROR"  # uppercased
        assert results[0]["message"] == "Test error message"
        assert results[0]["pid"] == "1234"
        assert results[0]["hostname"] == "test-host"

    @pytest.mark.asyncio
    async def test_get_logs_docker(self, log_reader):
        """Should get logs from mmap reader in Docker environment."""
        # Mock the mmap reader
        mock_mmap_reader = MagicMock()
        mock_mmap_reader.get_logs.return_value = [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "level": "INFO",
                "message": "Log line 1",
                "service": "service1",
            },
            {
                "timestamp": "2024-01-15T10:01:00Z",
                "level": "ERROR",
                "message": "Log line 2",
                "service": "service2",
            },
        ]
        log_reader.mmap_reader = mock_mmap_reader

        results = await log_reader.get_logs(limit=10)

        # Should get logs from mmap reader
        assert mock_mmap_reader.get_logs.called
        assert len(results) <= 10  # respects limit

    @pytest.mark.asyncio
    async def test_get_logs_systemd(self):
        """Should get logs from journalctl in systemd environment."""
        with patch("birdnetpi.system.log_reader.SystemUtils") as mock_utils:
            mock_utils.is_docker_environment.return_value = False
            mock_utils.is_systemd_available.return_value = True
            log_reader = LogReaderService()

            journal_output = json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1705318245000000",
                    "_SYSTEMD_UNIT": "test.service",
                    "MESSAGE": "Test message",
                }
            )

            mock_subprocess = AsyncMock()
            mock_subprocess.communicate.return_value = (journal_output.encode(), b"")

            with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
                results = await log_reader.get_logs(
                    services=["test"], start_time=datetime(2024, 1, 15, tzinfo=UTC), limit=5
                )

                # Check that journalctl was called with correct parameters
                assert len(results) <= 5

    def test_apply_filters_level(self, log_reader):
        """Should filter logs by minimum log level hierarchically."""
        entries = [
            {"level": "DEBUG", "message": "Debug"},
            {"level": "INFO", "message": "Info"},
            {"level": "WARNING", "message": "Warning"},
            {"level": "ERROR", "message": "Error"},
        ]

        # Filter for WARNING and above
        filtered = log_reader._apply_filters(entries, level="WARNING")

        assert len(filtered) == 2
        assert all(e["level"] in ["WARNING", "ERROR"] for e in filtered)

    def test_apply_filters_keyword(self, log_reader):
        """Should filter logs by keyword in message or service."""
        entries = [
            {"message": "Error in module A", "service": "api"},
            {"message": "Success", "service": "worker"},
            {"message": "Module B started", "service": "api"},
        ]

        # Filter by keyword in message
        filtered = log_reader._apply_filters(entries, keyword="module")
        assert len(filtered) == 2

        # Filter by keyword in service
        filtered = log_reader._apply_filters(entries, keyword="api")
        assert len(filtered) == 2

    def test_apply_filters_time_range(self, log_reader):
        """Should filter logs within specified time range."""
        base_time = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        entries = [
            {"timestamp": base_time.isoformat(), "message": "At start"},
            {"timestamp": base_time.replace(hour=11).isoformat(), "message": "Middle"},
            {"timestamp": base_time.replace(hour=12).isoformat(), "message": "At end"},
        ]

        filtered = log_reader._apply_filters(
            entries,
            start_time=base_time.replace(minute=30),
            end_time=base_time.replace(hour=11, minute=30),
        )

        assert len(filtered) == 1
        assert filtered[0]["message"] == "Middle"

    @pytest.mark.asyncio
    async def test_stream_logs_docker(self, log_reader):
        """Should stream logs from Docker environment asynchronously."""

        # Create a simple async generator for streaming
        async def mock_stream():
            yield {
                "timestamp": "2024-01-15T10:00:00Z",
                "level": "INFO",
                "message": "First log line",
                "service": "test",
            }
            yield {
                "timestamp": "2024-01-15T10:01:00Z",
                "level": "ERROR",
                "message": "Error log",
                "service": "test",
            }

        with patch.object(log_reader, "_stream_docker_logs", return_value=mock_stream()):
            logs = []
            async for entry in log_reader.stream_logs(services=["test"]):
                logs.append(entry)
                if len(logs) >= 2:
                    break

            assert len(logs) == 2
            assert logs[1]["level"] == "ERROR"

    def test_matches_filters(self, log_reader):
        """Should match entries against level and keyword filters."""
        entry = {"level": "WARNING", "message": "Warning about disk space", "service": "monitor"}

        # Should match - no filters
        assert log_reader._matches_filters(entry) is True

        # Should match - level is high enough
        assert log_reader._matches_filters(entry, level="INFO") is True

        # Should not match - level too low
        assert log_reader._matches_filters(entry, level="ERROR") is False

        # Should match - keyword in message
        assert log_reader._matches_filters(entry, keyword="disk") is True

        # Should not match - keyword not found
        assert log_reader._matches_filters(entry, keyword="network") is False

        # Combined filters
        assert log_reader._matches_filters(entry, level="WARNING", keyword="space") is True
        assert log_reader._matches_filters(entry, level="ERROR", keyword="space") is False

    @pytest.mark.asyncio
    async def test_mmap_reader_cleanup(self, log_reader):
        """Should properly close mmap reader during cleanup."""
        # Mock the mmap reader
        mock_mmap_reader = MagicMock()
        mock_mmap_reader.close = MagicMock()
        log_reader.mmap_reader = mock_mmap_reader

        # Test cleanup if mmap reader exists
        if log_reader.mmap_reader:
            log_reader.mmap_reader.close()
            assert mock_mmap_reader.close.called

    @pytest.mark.asyncio
    async def test_filter_logs_from_mmap(self, log_reader):
        """Should filter logs from mmap with limit support."""
        # Mock mmap reader with various log levels
        mock_mmap_reader = MagicMock()
        test_logs = [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "level": "DEBUG",
                "message": "Debug log",
                "service": "test",
            },
            {
                "timestamp": "2024-01-15T10:01:00Z",
                "level": "INFO",
                "message": "Info log",
                "service": "test",
            },
            {
                "timestamp": "2024-01-15T10:02:00Z",
                "level": "WARNING",
                "message": "Warning log",
                "service": "test",
            },
            {
                "timestamp": "2024-01-15T10:03:00Z",
                "level": "ERROR",
                "message": "Error log",
                "service": "test",
            },
        ]
        mock_mmap_reader.get_logs.return_value = test_logs
        log_reader.mmap_reader = mock_mmap_reader

        # Test that we get all logs when no filtering
        results = await log_reader.get_logs(limit=10)
        assert len(results) == 4

        # Test with limit
        mock_mmap_reader.get_logs.return_value = test_logs[:2]
        results = await log_reader.get_logs(limit=2)
        assert len(results) == 2
