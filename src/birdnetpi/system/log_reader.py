"""Log reading service supporting both Docker (supervisord) and SBC (systemd) deployments."""

import asyncio
import json
import logging
import mmap
import os
import struct
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from birdnetpi.system.system_utils import SystemUtils

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """Log levels with numeric values for filtering."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @property
    def numeric_value(self) -> int:
        """Get numeric value for level comparison."""
        return {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}[self.value]

    @classmethod
    def from_string(cls, level_str: str) -> "LogLevel":
        """Convert string to LogLevel, with fallback to INFO."""
        try:
            return cls(level_str.upper())
        except (ValueError, AttributeError):
            return cls.INFO


class MmapLogReader:
    """Memory-mapped file reader for logs from ring buffer."""

    def __init__(self, file_path: str = "/dev/shm/birdnetpi_logs.mmap", max_entries: int = 1000):
        """Initialize mmap reader.

        Args:
            file_path: Path to memory-mapped file
            max_entries: Maximum number of log entries in buffer
        """
        self.file_path = file_path
        self.max_entries = max_entries
        self.header_size = 16
        self.entry_size = 4096

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent logs from memory-mapped file.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of log entries
        """
        if not os.path.exists(self.file_path):
            return []

        logs = []
        try:
            with open(self.file_path, "rb") as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

                # Read header: write_pos, entry_count, current_index
                _write_pos, entry_count, current_index = struct.unpack(
                    "<QII", mm[: self.header_size]
                )

                # Read logs backwards from current position
                entries_to_read = min(limit, entry_count)
                for i in range(entries_to_read):
                    # Calculate index going backwards
                    idx = (current_index - i) % self.max_entries
                    if idx < 0:
                        idx += self.max_entries

                    entry_pos = self.header_size + (idx * self.entry_size)

                    # Read entry length and data
                    if entry_pos + 4 <= len(mm):
                        entry_len = struct.unpack("<I", mm[entry_pos : entry_pos + 4])[0]
                        if entry_len > 0 and entry_pos + 4 + entry_len <= len(mm):
                            entry_data = mm[entry_pos + 4 : entry_pos + 4 + entry_len]
                            try:
                                log_entry = json.loads(entry_data.decode("utf-8"))
                                logs.append(log_entry)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass

                mm.close()

        except Exception as e:
            logger.debug(f"Error reading from mmap: {e}")

        # Logs are already in newest-first order from reading backwards
        return logs


class LogReaderService:
    """Service for retrieving and processing system logs from Docker or SBC deployments."""

    def __init__(self) -> None:
        """Initialize the log reader service."""
        self.is_docker = SystemUtils.is_docker_environment()
        self.has_systemd = SystemUtils.is_systemd_available()
        self.mmap_reader = None
        if self.is_docker:
            # Try to initialize memcached reader for Docker environments
            try:
                self.mmap_reader = MmapLogReader()
            except Exception:
                logger.debug("Memcached not available for log reading")
        logger.info(
            f"LogReaderService initialized: docker={self.is_docker}, systemd={self.has_systemd}"
        )

    def _should_skip_line(self, line: str) -> bool:
        """Check if a log line should be skipped.

        Args:
            line: The log line to check

        Returns:
            True if the line should be skipped
        """
        stripped = line.strip()
        if not stripped:
            return True
        # Filter out supervisorctl interactive prompts
        if "==> Press Ctrl-C to exit <==" in stripped:
            return True
        if stripped == "Press Ctrl-C to exit":
            return True
        return False

    def _parse_json_log(self, line: str, service_name: str) -> dict[str, Any] | None:
        """Try to parse a log line as JSON.

        Args:
            line: The log line
            service_name: Default service name

        Returns:
            Parsed log entry or None if not JSON
        """
        if not line.strip().startswith("{"):
            return None

        try:
            entry = json.loads(line)
            # Ensure required fields
            if "timestamp" not in entry:
                entry["timestamp"] = datetime.now(UTC).isoformat()
            if "level" not in entry:
                entry["level"] = "INFO"
            if "service" not in entry:
                entry["service"] = service_name
            if "message" not in entry:
                entry["message"] = entry.get("msg", "")
            return entry
        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_text_log(self, line: str, service_name: str) -> dict[str, Any]:
        """Parse a plain text log line.

        Args:
            line: The log line
            service_name: Service name

        Returns:
            Parsed log entry
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": service_name,
            "level": "INFO",
            "message": line.strip(),
            "raw": True,  # Indicates this was not JSON
        }

        # Try to extract log level from common patterns
        for level in LogLevel:
            if level.value in line.upper():
                entry["level"] = level.value
                break

        return entry

    def parse_log_entry(self, line: str, service_name: str = "") -> dict[str, Any] | None:
        """Parse a log line into structured format.

        Args:
            line: Raw log line
            service_name: Name of the service (for context)

        Returns:
            Parsed log entry dict or None if unparseable
        """
        if self._should_skip_line(line):
            return None

        # Try JSON parsing first
        json_entry = self._parse_json_log(line, service_name)
        if json_entry:
            return json_entry

        # Fallback to text parsing
        return self._parse_text_log(line, service_name)

    def _parse_supervisord_logs(self, output: str, service_name: str = "") -> list[dict[str, Any]]:
        """Parse supervisord log output into structured entries.

        Args:
            output: Raw supervisord log output
            service_name: Name of the service

        Returns:
            List of parsed log entries
        """
        entries = []
        for line in output.splitlines():
            # Skip supervisorctl error messages about bad channels
            if "bad channel" in line.lower():
                continue
            if entry := self.parse_log_entry(line, service_name):
                entries.append(entry)
        return entries

    def _parse_journald_logs(self, output: str) -> list[dict[str, Any]]:
        """Parse journald log output into structured entries.

        Args:
            output: Raw journald output in JSON format

        Returns:
            List of parsed log entries
        """
        entries = []
        for line in output.splitlines():
            try:
                # journalctl -o json outputs one JSON object per line
                journal_entry = json.loads(line)
                entry = {
                    "timestamp": datetime.fromtimestamp(
                        int(journal_entry.get("__REALTIME_TIMESTAMP", 0)) / 1_000_000, UTC
                    ).isoformat(),
                    "service": journal_entry.get("_SYSTEMD_UNIT", "").replace(".service", ""),
                    "level": journal_entry.get("PRIORITY_TEXT", "INFO").upper(),
                    "message": journal_entry.get("MESSAGE", ""),
                    "pid": journal_entry.get("_PID"),
                    "hostname": journal_entry.get("_HOSTNAME"),
                }
                entries.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"Failed to parse journald entry: {e}")
        return entries

    async def get_logs(
        self,
        services: list[str] | None = None,
        level: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        keyword: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get historical logs with filtering.

        Args:
            services: Filter by service names
            level: Minimum log level to include
            start_time: Start of time range
            end_time: End of time range
            keyword: Search keyword in messages
            limit: Maximum entries to return

        Returns:
            List of filtered log entries
        """
        all_entries = []

        if self.is_docker:
            # Docker: Use supervisorctl to get logs
            all_entries = await self._get_docker_logs(services, limit)
        elif self.has_systemd:
            # SBC: Use journalctl to get logs
            all_entries = await self._get_systemd_logs(services, start_time, end_time, limit)
        else:
            # Fallback: Try to read from standard log files
            all_entries = await self._get_file_logs(services, limit)

        # Apply filters
        filtered = self._apply_filters(all_entries, level, start_time, end_time, keyword)

        # Apply limit
        return filtered[:limit]

    async def _get_docker_logs(
        self, services: list[str] | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Get logs from Docker container via memcached.

        The supervisor-wrapper writes logs to both stdout (for Docker logs)
        and memcached (for internal access). This method reads from memcached.

        Args:
            services: Service names to filter (not currently used)
            limit: Maximum lines to return

        Returns:
            List of log entries
        """
        if self.mmap_reader:
            # Read from memory-mapped ring buffer
            return self.mmap_reader.get_logs(limit=limit)

        # Fallback if mmap is not available
        logger.debug(
            "Memory-mapped log file not available, logs cannot be retrieved from container"
        )
        return []

    async def _get_systemd_logs(
        self,
        services: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get logs from systemd using journalctl.

        Args:
            services: Service names to filter
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum entries

        Returns:
            List of log entries
        """
        cmd = [
            "journalctl",
            "--no-pager",
            "-o",
            "json",
            "-n",
            str(limit),
        ]

        # Add service filters
        if services:
            for service in services:
                cmd.extend(["-u", f"{service}.service"])

        # Add time filters
        if start_time:
            cmd.extend(["--since", start_time.isoformat()])
        if end_time:
            cmd.extend(["--until", end_time.isoformat()])

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            return self._parse_journald_logs(stdout.decode())
        except Exception as e:
            logger.error(f"Failed to get systemd logs: {e}")
            return []

    async def _get_file_logs(
        self, services: list[str] | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Fallback: Read logs from standard log files.

        Args:
            services: Service names (unused in fallback)
            limit: Maximum entries

        Returns:
            List of log entries
        """
        # This is a fallback for environments without supervisord or systemd
        # Would typically read from /var/log or configured log directory
        logger.warning("Using fallback file-based log reading")
        return []

    def _apply_filters(
        self,
        entries: list[dict[str, Any]],
        level: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Apply filters to log entries.

        Args:
            entries: Log entries to filter
            level: Minimum log level
            start_time: Start of time range
            end_time: End of time range
            keyword: Search keyword

        Returns:
            Filtered list of entries
        """
        filtered = entries

        # Filter by log level (hierarchical)
        if level:
            min_level = LogLevel.from_string(level)
            filtered = [
                e
                for e in filtered
                if LogLevel.from_string(e.get("level", "INFO")).numeric_value
                >= min_level.numeric_value
            ]

        # Filter by time range
        if start_time or end_time:
            filtered_by_time = []
            for entry in filtered:
                try:
                    entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
                    if start_time and entry_time < start_time:
                        continue
                    if end_time and entry_time > end_time:
                        continue
                    filtered_by_time.append(entry)
                except (ValueError, TypeError):
                    # Keep entries with unparseable timestamps
                    filtered_by_time.append(entry)
            filtered = filtered_by_time

        # Filter by keyword
        if keyword:
            keyword_lower = keyword.lower()
            filtered = [
                e
                for e in filtered
                if keyword_lower in e.get("message", "").lower()
                or keyword_lower in e.get("service", "").lower()
            ]

        # Sort by timestamp (newest first)
        filtered.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )

        return filtered

    async def stream_logs(
        self,
        services: list[str] | None = None,
        level: str | None = None,
        keyword: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream logs in real-time.

        Args:
            services: Services to monitor
            level: Minimum log level
            keyword: Keyword filter

        Yields:
            Log entries as they arrive
        """
        if self.is_docker:
            # Docker: tail supervisorctl logs
            async for entry in self._stream_docker_logs(services):
                if self._matches_filters(entry, level, keyword):
                    yield entry
        elif self.has_systemd:
            # SBC: follow journalctl
            async for entry in self._stream_systemd_logs(services):
                if self._matches_filters(entry, level, keyword):
                    yield entry
        else:
            # Fallback: poll log files
            logger.warning("No streaming support in fallback mode")
            while True:
                await asyncio.sleep(1)
                # Could implement file tailing here

    def _read_log_entry_from_mmap(self, mm: mmap.mmap, idx: int) -> dict[str, Any] | None:
        """Read a single log entry from memory map at given index.

        Args:
            mm: Memory-mapped file object
            idx: Entry index to read

        Returns:
            Log entry dict or None if read fails
        """
        if not self.mmap_reader:
            return None
        entry_pos = self.mmap_reader.header_size + (idx * self.mmap_reader.entry_size)

        if entry_pos + 4 > len(mm):
            return None

        entry_len = struct.unpack("<I", mm[entry_pos : entry_pos + 4])[0]
        if entry_len <= 0 or entry_pos + 4 + entry_len > len(mm):
            return None

        entry_data = mm[entry_pos + 4 : entry_pos + 4 + entry_len]
        try:
            return json.loads(entry_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _calculate_new_entries_count(self, current_index: int, last_index: int) -> int:
        """Calculate number of new entries since last index.

        Args:
            current_index: Current ring buffer index
            last_index: Previously seen index

        Returns:
            Number of new entries
        """
        if not self.mmap_reader:
            return 0
        if current_index > last_index:
            return current_index - last_index
        else:
            # Wrapped around
            return (self.mmap_reader.max_entries - last_index) + current_index

    async def _yield_initial_entries(
        self,
        mm: mmap.mmap,
        current_index: int,
        entry_count: int,
        yielded_entries: set[str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield initial set of log entries when starting stream.

        Args:
            mm: Memory-mapped file object
            current_index: Current ring buffer index
            entry_count: Total number of entries
            yielded_entries: Set tracking already yielded entries

        Yields:
            Initial log entries
        """
        if not self.mmap_reader:
            return
        for i in range(min(10, entry_count)):
            idx = (current_index - i) % self.mmap_reader.max_entries
            if idx < 0:
                idx += self.mmap_reader.max_entries

            log_entry = self._read_log_entry_from_mmap(mm, idx)
            if log_entry:
                entry_id = log_entry.get("timestamp", "")
                if entry_id and entry_id not in yielded_entries:
                    yielded_entries.add(entry_id)
                    yield log_entry

    async def _yield_new_entries(
        self,
        mm: mmap.mmap,
        last_index: int,
        num_new: int,
        yielded_entries: set[str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield new log entries since last index.

        Args:
            mm: Memory-mapped file object
            last_index: Previously seen index
            num_new: Number of new entries to yield
            yielded_entries: Set tracking already yielded entries

        Yields:
            New log entries
        """
        if not self.mmap_reader:
            return
        for i in range(min(num_new, 100)):  # Limit to 100 at a time
            idx = (last_index + i + 1) % self.mmap_reader.max_entries

            log_entry = self._read_log_entry_from_mmap(mm, idx)
            if log_entry:
                entry_id = log_entry.get("timestamp", "")
                if entry_id and entry_id not in yielded_entries:
                    yielded_entries.add(entry_id)
                    yield log_entry

                    # Keep set size limited
                    if len(yielded_entries) > 2000:
                        # Remove oldest entries
                        yielded_entries.clear()
                        yielded_entries.update(list(yielded_entries)[-1000:])

    async def _stream_docker_logs(  # noqa: C901
        self, services: list[str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream logs from Docker container via memcached polling.

        Polls memcached for new log entries in the ring buffer.

        Args:
            services: Service names to filter (not currently used)

        Yields:
            Log entries as they arrive
        """
        if not self.mmap_reader:
            logger.warning("Memory-mapped log file not available, cannot stream logs")
            return

        last_index = -1
        yielded_entries: set[str] = set()  # Track yielded entries to avoid duplicates

        try:
            while True:
                try:
                    if not os.path.exists(self.mmap_reader.file_path):
                        await asyncio.sleep(1)
                        continue

                    with open(self.mmap_reader.file_path, "rb") as f:
                        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

                        # Read header
                        _write_pos, entry_count, current_index = struct.unpack(
                            "<QII", mm[: self.mmap_reader.header_size]
                        )

                        # If this is our first read, start from current position
                        if last_index == -1:
                            last_index = current_index
                            # Yield last 10 entries to start
                            async for entry in self._yield_initial_entries(
                                mm, current_index, entry_count, yielded_entries
                            ):
                                yield entry

                        # Check for new entries
                        elif current_index != last_index:
                            num_new = self._calculate_new_entries_count(current_index, last_index)

                            # Yield new entries
                            async for entry in self._yield_new_entries(
                                mm, last_index, num_new, yielded_entries
                            ):
                                yield entry

                            last_index = current_index

                        mm.close()

                    # Sleep before next poll
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.debug(f"Error reading mmap during stream: {e}")
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error streaming from mmap: {e}")

    # NOTE: The following methods were used for supervisorctl tail approach
    # but are kept for potential future use with file-based logging

    # async def _create_tail_processes(...) - removed
    # async def _read_from_processes(...) - removed
    # async def _read_single_process(...) - removed
    # async def _cleanup_processes(...) - removed

    async def _stream_systemd_logs(
        self, services: list[str] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream logs from systemd using journalctl -f.

        Args:
            services: Services to monitor

        Yields:
            Log entries as they arrive
        """
        cmd = [
            "journalctl",
            "--no-pager",
            "-f",  # Follow
            "-o",
            "json",
        ]

        # Add service filters
        if services:
            for service in services:
                cmd.extend(["-u", f"{service}.service"])

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            while True:
                if process.stdout:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    try:
                        journal_entry = json.loads(line.decode())
                        entry = {
                            "timestamp": datetime.fromtimestamp(
                                int(journal_entry.get("__REALTIME_TIMESTAMP", 0)) / 1_000_000,
                                UTC,
                            ).isoformat(),
                            "service": journal_entry.get("_SYSTEMD_UNIT", "").replace(
                                ".service", ""
                            ),
                            "level": journal_entry.get("PRIORITY_TEXT", "INFO").upper(),
                            "message": journal_entry.get("MESSAGE", ""),
                        }
                        yield entry
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"Failed to parse journal entry: {e}")
        finally:
            if process:
                try:
                    process.terminate()
                    await process.wait()
                except Exception:
                    pass

    def _matches_filters(
        self,
        entry: dict[str, Any],
        level: str | None = None,
        keyword: str | None = None,
    ) -> bool:
        """Check if entry matches filters.

        Args:
            entry: Log entry to check
            level: Minimum log level
            keyword: Keyword to search

        Returns:
            True if entry matches all filters
        """
        # Check log level
        if level:
            min_level = LogLevel.from_string(level)
            entry_level = LogLevel.from_string(entry.get("level", "INFO"))
            if entry_level.numeric_value < min_level.numeric_value:
                return False

        # Check keyword
        if keyword:
            keyword_lower = keyword.lower()
            message = entry.get("message", "").lower()
            service = entry.get("service", "").lower()
            if keyword_lower not in message and keyword_lower not in service:
                return False

        return True
