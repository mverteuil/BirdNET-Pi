"""WebSocket routes for real-time communication."""

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/notifications")
async def websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time notifications and updates."""
    await websocket.accept()
    request.app.extra["active_websockets"].add(websocket)  # Add new connection
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        request.app.extra["active_websockets"].remove(websocket)  # Remove disconnected client
        logger.info("Client disconnected")


# Audio and spectrogram WebSocket endpoints are now handled by the standalone
# audio_websocket_daemon for better service independence and performance.
# These routes have been moved to the daemon running on port 9001 and are
# proxied by Caddy at /ws/audio and /ws/spectrogram.
