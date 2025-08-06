"""WebSocket routes for real-time communication."""

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/notifications")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time notifications and updates."""
    try:
        await websocket.accept()
        logger.info("WebSocket client connected")
        
        # Try to get active websockets from app extra (if available)
        try:
            app = websocket.app
            if hasattr(app, 'extra') and app.extra and 'active_websockets' in app.extra:
                app.extra["active_websockets"].add(websocket)
                logger.info("WebSocket added to active connections")
        except Exception as e:
            logger.warning(f"Could not add to active websockets: {e}")
        
        # Keep connection alive
        while True:
            message = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {message}")
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        # Try to remove from active websockets on disconnect
        try:
            app = websocket.app
            if hasattr(app, 'extra') and app.extra and 'active_websockets' in app.extra:
                app.extra["active_websockets"].discard(websocket)
        except Exception as e:
            logger.warning(f"Could not remove from active websockets: {e}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        # Try to remove from active websockets on any error
        try:
            app = websocket.app
            if hasattr(app, 'extra') and app.extra and 'active_websockets' in app.extra:
                app.extra["active_websockets"].discard(websocket)
        except Exception:
            pass


# Audio and spectrogram WebSocket endpoints are now handled by the standalone
# audio_websocket_daemon for better service independence and performance.
# These routes have been moved to the daemon running on port 9001 and are
# proxied by Caddy at /ws/audio and /ws/spectrogram.
