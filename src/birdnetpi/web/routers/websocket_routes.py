"""WebSocket routes for real-time communication."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from birdnetpi.services.notification_service import NotificationService
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/notifications")
@inject
async def websocket_endpoint(
    websocket: WebSocket,
    notification_service: NotificationService = Depends(Provide[Container.notification_service])
) -> None:
    """Handle WebSocket connections for real-time notifications and updates."""
    try:
        await websocket.accept()
        logger.info("WebSocket client connected")
        
        # Add to active websockets through the notification service
        notification_service.add_websocket(websocket)
        logger.info("WebSocket added to notification service")
        
        # Keep connection alive
        while True:
            message = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {message}")
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        notification_service.remove_websocket(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        notification_service.remove_websocket(websocket)


# Audio and spectrogram WebSocket endpoints are now handled by the standalone
# audio_websocket_daemon for better service independence and performance.
# These routes have been moved to the daemon running on port 9001 and are
# proxied by Caddy at /ws/audio and /ws/spectrogram.
