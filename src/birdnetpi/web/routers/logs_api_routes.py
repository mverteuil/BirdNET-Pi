"""API routes for log viewing and streaming."""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from birdnetpi.system.log_reader import LogReaderService
from birdnetpi.utils.auth import require_admin
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS, LogEntry
from birdnetpi.web.models.services import LogsResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs", response_model=LogsResponse)
@require_admin
@inject
async def get_logs(
    request: Request,
    log_reader: Annotated[LogReaderService, Depends(Provide[Container.log_reader])],
    start_time: Annotated[datetime | None, Query(description="Start of time range")] = None,
    end_time: Annotated[datetime | None, Query(description="End of time range")] = None,
    limit: Annotated[int, Query(ge=1, le=10000, description="Maximum entries")] = 1000,
) -> LogsResponse:
    """Get historical logs within time range.

    All filtering is now done client-side for consistency between
    fetched and streamed logs.

    Args:
        request: FastAPI request object (required by authentication decorator)
        log_reader: Injected log reader service
        start_time: Start of time range
        end_time: End of time range
        limit: Maximum number of entries

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
                    logger.debug("Skipping non-dict log entry: %s", log)
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
                logger.debug("Failed to parse log entry: %s", e)
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

        return LogsResponse(
            logs=entries,
            total=len(entries),
            limit=limit,
            levels=LOG_LEVELS,
            error=None,
        )
    except Exception as e:
        logger.error("Failed to get logs: %s", e, exc_info=True)
        return LogsResponse(
            logs=[],
            total=0,
            limit=limit,
            levels=LOG_LEVELS,
            error=str(e),
        )


@router.get("/logs/stream")
@require_admin
@inject
async def stream_logs(
    request: Request,
    log_reader: Annotated[LogReaderService, Depends(Provide[Container.log_reader])],
) -> StreamingResponse:
    """Stream logs using Server-Sent Events (SSE).

    All filtering is done client-side for consistency between
    fetched and streamed logs.

    Args:
        request: FastAPI request object (required by authentication decorator)
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
                    logger.debug("Failed to format log entry: %s", e)
                    # Send raw entry
                    yield f"data: {json.dumps(log_entry, default=str)}\n\n"

        except Exception as e:
            logger.error("Error in log streaming: %s", e, exc_info=True)
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
@require_admin
async def get_log_levels(request: Request) -> list[dict[str, Any]]:
    """Get available log levels with display information.

    Returns:
        List of log level information for UI
    """
    return [level.model_dump() for level in LOG_LEVELS]
