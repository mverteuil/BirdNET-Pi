"""API routes for log viewing and streaming."""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from birdnetpi.system.log_reader import LogReaderService
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS, LogEntry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs")
@inject
async def get_logs(
    start_time: datetime | None = Query(None, description="Start of time range"),  # noqa: B008
    end_time: datetime | None = Query(None, description="End of time range"),  # noqa: B008
    limit: int = Query(1000, ge=1, le=10000, description="Maximum entries"),
    log_reader: LogReaderService = Depends(  # noqa: B008
        Provide[Container.log_reader]
    ),
) -> dict[str, Any]:
    """Get historical logs within time range.

    All filtering is now done client-side for consistency between
    fetched and streamed logs.

    Args:
        start_time: Start of time range
        end_time: End of time range
        limit: Maximum number of entries
        log_reader: Injected log reader service

    Returns:
        Dictionary with logs and metadata
    """
    try:
        # Get logs with only time filtering (all other filters handled client-side)
        logs = await log_reader.get_logs(
            services=None,  # No service filtering
            level=None,  # No level filtering
            start_time=start_time,
            end_time=end_time,
            keyword=None,  # No keyword filtering
            limit=limit,
        )

        # Convert to LogEntry models
        entries = []
        for log in logs[:limit]:
            try:
                # Skip non-dict entries
                if not isinstance(log, dict):
                    logger.debug(f"Skipping non-dict log entry: {log}")
                    continue

                # Map fields from supervisor-wrapper format to LogEntry format
                mapped_log = {
                    "timestamp": log.get("timestamp", datetime.now().isoformat()),
                    "service": log.get(
                        "service", log.get("logger", "unknown")
                    ),  # Prefer service over logger
                    "level": log.get("level", "INFO"),
                    "message": log.get("event", log.get("message", str(log))),
                }

                # Add any extra fields
                extra = {
                    k: v
                    for k, v in log.items()
                    if k not in ["timestamp", "logger", "level", "event", "service", "message"]
                }
                if extra:
                    mapped_log["extra"] = extra

                # Parse timestamp if it's a string
                if isinstance(mapped_log["timestamp"], str):
                    mapped_log["timestamp"] = datetime.fromisoformat(
                        mapped_log["timestamp"].replace("Z", "+00:00")
                    )

                entries.append(LogEntry(**mapped_log))
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse log entry: {e}")
                # Create a basic entry for dict logs that failed parsing
                if isinstance(log, dict):
                    entries.append(
                        LogEntry(
                            timestamp=datetime.now(),
                            service=log.get("service", "unknown"),
                            level=log.get("level", "INFO"),
                            message=str(log),
                            raw=True,
                        )
                    )

        return {
            "logs": [entry.model_dump() for entry in entries],
            "total": len(entries),
            "limit": limit,
            "levels": LOG_LEVELS,
        }
    except Exception as e:
        logger.error(f"Failed to get logs: {e}", exc_info=True)
        return {
            "logs": [],
            "total": 0,
            "limit": limit,
            "error": str(e),
        }


@router.get("/logs/stream")
@inject
async def stream_logs(
    log_reader: LogReaderService = Depends(  # noqa: B008
        Provide[Container.log_reader]
    ),
) -> StreamingResponse:
    """Stream logs using Server-Sent Events (SSE).

    All filtering is done client-side for consistency between
    fetched and streamed logs.

    Args:
        log_reader: Injected log reader service

    Returns:
        SSE streaming response
    """

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events from log stream."""
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            # Stream all logs (filtering done client-side)
            async for log_entry in log_reader.stream_logs(
                services=None,  # No service filtering
                level=None,  # No level filtering
                keyword=None,  # No keyword filtering
            ):
                try:
                    # Map fields from supervisor-wrapper format to LogEntry format
                    mapped_log = {
                        "timestamp": log_entry.get("timestamp", datetime.now().isoformat()),
                        "service": log_entry.get(
                            "service", log_entry.get("logger", "unknown")
                        ),  # Prefer service over logger
                        "level": log_entry.get("level", "INFO"),
                        "message": log_entry.get("event", log_entry.get("message", str(log_entry))),
                    }

                    # Add any extra fields
                    extra = {
                        k: v
                        for k, v in log_entry.items()
                        if k not in ["timestamp", "logger", "level", "event", "service", "message"]
                    }
                    if extra:
                        mapped_log["extra"] = extra

                    # Convert to LogEntry for validation
                    if isinstance(mapped_log["timestamp"], str):
                        mapped_log["timestamp"] = datetime.fromisoformat(
                            mapped_log["timestamp"].replace("Z", "+00:00")
                        )

                    entry = LogEntry(**mapped_log)

                    # Send as SSE event
                    event_data = json.dumps(entry.model_dump(), default=str)
                    yield f"data: {event_data}\n\n"
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to format log entry: {e}")
                    # Send raw entry
                    yield f"data: {json.dumps(log_entry, default=str)}\n\n"

        except Exception as e:
            logger.error(f"Error in log streaming: {e}", exc_info=True)
            # Send error event
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Send disconnect event
            yield f"event: disconnected\ndata: {json.dumps({'status': 'disconnected'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@router.get("/logs/levels")
async def get_log_levels() -> list[dict[str, Any]]:
    """Get available log levels with display information.

    Returns:
        List of log level information for UI
    """
    return [level.model_dump() for level in LOG_LEVELS]
