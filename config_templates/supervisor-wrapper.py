#!/usr/bin/env python3
import asyncio
import json
import mmap
import os
import re
import signal
import struct
import sys
from datetime import datetime
from types import FrameType


class RingBufferLogger:
    """Memory-mapped ring buffer for log storage."""

    def __init__(
        self,
        file_path: str = "/dev/shm/birdnetpi_logs.mmap",
        size: int = 10 * 1024 * 1024,
        max_entries: int = 1000,
    ):
        """Initialize memory-mapped ring buffer.

        Args:
            file_path: Path to memory-mapped file (use /dev/shm for RAM)
            size: Total size of buffer in bytes (default 10MB)
            max_entries: Maximum number of log entries to keep
        """
        self.file_path = file_path
        self.size = size
        self.max_entries = max_entries
        self.mmap_file = None
        self.mm = None

        # Header format: write_pos (8 bytes), entry_count (4 bytes), current_index (4 bytes)
        self.header_size = 16
        self.entry_size = 4096  # Fixed size per entry

        try:
            self._init_mmap()
        except Exception as e:
            print(f"Failed to initialize ring buffer: {e}", file=sys.stderr)

    def _init_mmap(self) -> None:
        """Initialize the memory-mapped file."""
        # Create or open the file
        if not os.path.exists(self.file_path):
            # Create new file with initial size
            with open(self.file_path, "wb") as f:
                f.write(b"\0" * self.size)

        # Open for memory mapping
        self.mmap_file = open(self.file_path, "r+b")
        self.mm = mmap.mmap(self.mmap_file.fileno(), self.size)

        # Initialize header if new file
        if self.mm[:4] == b"\0\0\0\0":
            self.mm[: self.header_size] = struct.pack("<QII", self.header_size, 0, 0)

    def add_log(self, log_entry: dict) -> None:
        """Add a log entry to the ring buffer.

        Args:
            log_entry: JSON-serializable log entry dict
        """
        if not self.mm:
            return

        try:
            # Serialize entry
            entry_json = json.dumps(log_entry)
            entry_bytes = entry_json.encode("utf-8")

            # Truncate if too long
            if len(entry_bytes) > self.entry_size - 4:
                entry_bytes = entry_bytes[: self.entry_size - 4]

            # Read current header
            _write_pos, entry_count, current_index = struct.unpack(
                "<QII", self.mm[: self.header_size]
            )

            # Calculate position for this entry
            current_index = (current_index + 1) % self.max_entries
            entry_pos = self.header_size + (current_index * self.entry_size)

            # Make sure we don't write past the end
            if entry_pos + self.entry_size > self.size:
                return

            # Write entry (length prefix + data)
            self.mm[entry_pos : entry_pos + 4] = struct.pack("<I", len(entry_bytes))
            self.mm[entry_pos + 4 : entry_pos + 4 + len(entry_bytes)] = entry_bytes

            # Update header
            entry_count = min(entry_count + 1, self.max_entries)
            self.mm[: self.header_size] = struct.pack("<QII", entry_pos, entry_count, current_index)

            # Flush changes
            self.mm.flush()

        except Exception:
            # Silently fail to avoid blocking
            pass

    def close(self) -> None:
        """Close the memory-mapped file."""
        if self.mm:
            try:
                self.mm.close()
            except Exception:
                pass
            self.mm = None

        if self.mmap_file:
            try:
                self.mmap_file.close()
            except Exception:
                pass
            self.mmap_file = None


# Service mapping patterns - ordered by priority (first match wins)
SERVICE_PATTERNS = [
    # Daemons - most specific
    (re.compile(r".*audio_capture_daemon.*"), "audio_capture"),
    (re.compile(r".*audio_analysis_daemon.*"), "audio_analysis"),
    (re.compile(r".*audio_websocket_daemon.*"), "audio_websocket"),
    # Audio module with sub-modules
    (re.compile(r"birdnetpi\.audio\.capture.*"), "audio_capture"),
    (re.compile(r"birdnetpi\.audio\.analysis.*"), "audio_analysis"),
    (re.compile(r"birdnetpi\.audio\.websocket.*"), "audio_websocket"),
    # Web and API modules (including detection queries/views)
    (re.compile(r"birdnetpi\.web\..*"), "fastapi"),
    (re.compile(r"birdnetpi\.detections\..*"), "fastapi"),  # Detection queries are from web
    (re.compile(r"birdnetpi\.analytics\..*"), "fastapi"),  # Analytics/presentation also from web
    (re.compile(r"uvicorn.*"), "fastapi"),
    # Supporting modules (usually called from web)
    (
        re.compile(
            r"birdnetpi\.(notifications|location|config|database|system|utils|species|i18n)\..*"
        ),
        "fastapi",
    ),
    # External services
    (re.compile(r"supervisord.*"), "supervisord"),
    (re.compile(r"(admin|http\.handlers|http\.log|tls).*"), "caddy"),
]


def get_service_from_logger(logger_name: str) -> str:
    """Map logger name to service name using pattern matching."""
    for pattern, service in SERVICE_PATTERNS:
        if pattern.match(logger_name):
            return service
    return "system"  # Default fallback


def parse_supervisord_log(line: str) -> dict[str, str]:
    """Parse supervisord log format: 2024-01-01 12:00:00,123 LEVEL message"""
    pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) (\w+) (.+)"
    match = re.match(pattern, line.strip())

    if match:
        date_part, ms, level, message = match.groups()
        timestamp = f"{date_part.replace(' ', 'T')}.{ms}Z"

        # Extract service name from supervisord messages if present
        service = "supervisord"
        if "spawned: '" in message or "entered RUNNING state" in message or "exited:" in message:
            # Extract service name from messages like "spawned: 'audio_capture' with pid 123"
            service_match = re.search(r"'([^']+)'", message)
            if service_match:
                service = service_match.group(1)

        return {
            "event": message.strip(),
            "level": level.lower(),
            "logger": "supervisord",
            "service": service,
            "timestamp": timestamp,
        }
    else:
        return {
            "event": line.strip(),
            "level": "info",
            "logger": "supervisord",
            "service": "supervisord",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


def is_supervisord_log(line: str) -> bool:
    """Check if a line is a supervisord log (vs application log)"""
    pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \w+ "
    return bool(re.match(pattern, line.strip()))


def is_json(line: str) -> bool:
    """Check if line is valid JSON"""
    try:
        json.loads(line)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def parse_uvicorn_log(line: str) -> dict[str, str] | None:
    """Parse uvicorn log format: LEVEL:     message"""
    pattern = r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):\s+(.+)"
    match = re.match(pattern, line.strip())

    if match:
        level, message = match.groups()
        return {
            "event": message.strip(),
            "level": level.lower(),
            "logger": "uvicorn",
            "service": "fastapi",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    return None


def parse_log_line(line_str: str) -> dict[str, str] | None:
    """Parse a single log line into JSON format.

    Args:
        line_str: The log line to parse

    Returns:
        Parsed log entry as dict or None if parsing fails
    """
    if not line_str:
        return None

    if is_supervisord_log(line_str):
        return parse_supervisord_log(line_str)

    if is_json(line_str):
        try:
            json_log = json.loads(line_str)
            # Add service name if not present (for services that don't set it)
            if "service" not in json_log and "logger" in json_log:
                json_log["service"] = get_service_from_logger(json_log["logger"])
            return json_log
        except Exception:
            return None

    uvicorn_log = parse_uvicorn_log(line_str)
    if uvicorn_log:
        return uvicorn_log

    # Wrap other plain text
    return {
        "event": line_str,
        "level": "info",
        "logger": "undefined",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def output_log(
    json_log: dict[str, str] | None, ring_buffer: RingBufferLogger | None = None
) -> None:
    """Output log to stdout and optionally to ring buffer.

    Args:
        json_log: The log entry to output
        ring_buffer: Optional ring buffer to write to
    """
    if json_log:
        # Print to stdout as before
        print(json.dumps(json_log), flush=True)

        # Also write to ring buffer if available
        if ring_buffer:
            ring_buffer.add_log(json_log)


async def stream_reader(
    stream: asyncio.StreamReader | None,
    stream_name: str,
    ring_buffer: RingBufferLogger | None = None,
) -> None:
    """Async reader to process lines from stream."""
    if stream is None:
        return

    while True:
        try:
            line = await stream.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            json_log = parse_log_line(line_str)
            output_log(json_log, ring_buffer)

        except asyncio.CancelledError:
            break
        except Exception:
            pass


def initialize_ring_buffer() -> RingBufferLogger | None:
    """Initialize the ring buffer logger.

    Returns:
        RingBufferLogger instance or None if initialization fails
    """
    try:
        ring_buffer = RingBufferLogger()
        startup_log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "info",
            "logger": "supervisord-wrapper",
            "message": "Ring buffer logger initialized successfully",
        }
        print(json.dumps(startup_log), flush=True)
        return ring_buffer
    except Exception as e:
        error_log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "warning",
            "logger": "supervisord-wrapper",
            "message": f"Ring buffer logger not available: {e}",
        }
        print(json.dumps(error_log), flush=True)
        return None


async def start_supervisord(
    cmd: list[str], env: dict[str, str]
) -> asyncio.subprocess.Process | None:
    """Start the supervisord process.

    Args:
        cmd: Command to execute
        env: Environment variables

    Returns:
        Process instance or None if startup fails
    """
    try:
        return await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
    except Exception:
        return None


async def handle_graceful_shutdown(
    process: asyncio.subprocess.Process, shutdown_event: asyncio.Event
) -> int:
    """Handle graceful shutdown of supervisord.

    Args:
        process: The supervisord process
        shutdown_event: Event signaling shutdown request

    Returns:
        Exit code from the process
    """
    process_task = asyncio.create_task(process.wait())
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, _pending = await asyncio.wait(
        [process_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
    )

    if shutdown_task in done:
        # We got a shutdown signal, wait for graceful termination
        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=30)
            graceful_log = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "info",
                "logger": "supervisord-wrapper",
                "message": f"Supervisord terminated gracefully with code {return_code}",
            }
            print(json.dumps(graceful_log), flush=True)
        except TimeoutError:
            # Force kill if graceful shutdown times out
            force_log = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "warning",
                "logger": "supervisord-wrapper",
                "message": "Graceful shutdown timed out, forcing termination",
            }
            print(json.dumps(force_log), flush=True)
            process.kill()
            return_code = await process.wait()
    else:
        # Process ended naturally
        return_code = await process_task

    return return_code


async def main() -> int:
    """Run supervisord and convert its logs to JSON while preserving application logs."""
    cmd = [
        "/usr/bin/supervisord",
        "-c",
        "/etc/supervisor/supervisord.conf",
        "-u",
        "birdnetpi",
    ]

    env = os.environ.copy()
    env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})

    # Initialize ring buffer logger
    ring_buffer = initialize_ring_buffer()

    # Start supervisord process
    process = await start_supervisord(cmd, env)
    if not process:
        if ring_buffer:
            ring_buffer.close()
        return 1

    # Set up signal handlers to forward to supervisord
    shutdown_event = asyncio.Event()

    def signal_handler(sig: int, frame: FrameType | None = None) -> None:
        """Handle SIGTERM and SIGINT by forwarding to supervisord"""
        # Log the shutdown signal
        shutdown_log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "info",
            "logger": "supervisord-wrapper",
            "message": f"Received {signal.Signals(sig).name}, forwarding to supervisord",
        }
        print(json.dumps(shutdown_log), flush=True)

        # Send SIGTERM to supervisord (it handles this gracefully)
        if process.returncode is None:
            process.terminate()
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # For asyncio compatibility
    loop = asyncio.get_event_loop()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        # Process both streams
        stdout_task = asyncio.create_task(stream_reader(process.stdout, "STDOUT", ring_buffer))
        stderr_task = asyncio.create_task(stream_reader(process.stderr, "STDERR", ring_buffer))

        # Handle graceful shutdown
        return_code = await handle_graceful_shutdown(process, shutdown_event)

        # Cancel the stream processing tasks
        stdout_task.cancel()
        stderr_task.cancel()

        try:
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        except Exception:
            pass

        # Clean up ring buffer
        if ring_buffer:
            ring_buffer.close()

        return return_code

    except Exception as e:
        error_log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "error",
            "logger": "supervisord-wrapper",
            "message": f"Unexpected error: {e!s}",
        }
        print(json.dumps(error_log), flush=True)
        if process.returncode is None:
            process.kill()
            await process.wait()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(130)
