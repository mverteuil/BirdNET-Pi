#!/usr/bin/env python3
import asyncio
import json
import os
import re
import signal
import sys
from datetime import datetime
from types import FrameType


def parse_supervisord_log(line: str) -> dict[str, str]:
    """Parse supervisord log format: 2024-01-01 12:00:00,123 LEVEL message"""
    pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) (\w+) (.+)"
    match = re.match(pattern, line.strip())

    if match:
        date_part, ms, level, message = match.groups()
        timestamp = f"{date_part.replace(' ', 'T')}.{ms}Z"
        return {
            "event": message.strip(),
            "level": level.lower(),
            "logger": "supervisord",
            "timestamp": timestamp,
        }
    else:
        return {
            "event": line.strip(),
            "level": "info",
            "logger": "supervisord",
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
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    return None


async def stream_reader(stream: asyncio.StreamReader | None, stream_name: str) -> None:
    """Async reader to process lines from stream"""
    if stream is None:
        return

    while True:
        try:
            line = await stream.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            if line_str:
                if is_supervisord_log(line_str):
                    json_log = parse_supervisord_log(line_str)
                    print(json.dumps(json_log), flush=True)
                elif is_json(line_str):
                    print(line_str, flush=True)
                elif uvicorn_log := parse_uvicorn_log(line_str):
                    print(json.dumps(uvicorn_log), flush=True)
                else:
                    # Wrap other plain text
                    wrapped_log = {
                        "event": line_str,
                        "level": "info",
                        "logger": "undefined",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    print(json.dumps(wrapped_log), flush=True)

        except asyncio.CancelledError:
            break
        except Exception:
            pass


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

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
    except Exception:
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
        stdout_task = asyncio.create_task(stream_reader(process.stdout, "STDOUT"))
        stderr_task = asyncio.create_task(stream_reader(process.stderr, "STDERR"))

        # Wait for either process completion or shutdown signal
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

        # Cancel the stream processing tasks
        stdout_task.cancel()
        stderr_task.cancel()

        try:
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        except Exception:
            pass

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
