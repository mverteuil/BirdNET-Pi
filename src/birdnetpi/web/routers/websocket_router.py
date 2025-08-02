"""WebSocket routes for real-time communication."""

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time updates."""
    await websocket.accept()
    request.app.state.active_websockets.add(websocket)  # Add new connection
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        request.app.state.active_websockets.remove(websocket)  # Remove disconnected client
        logger.info("Client disconnected")


@router.websocket("/audio")
async def audio_websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time audio streaming."""
    await websocket.accept()
    await request.app.state.audio_websocket_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await request.app.state.audio_websocket_service.disconnect_websocket(websocket)
        logger.info("Audio WebSocket client disconnected")


@router.websocket("/spectrogram")
async def spectrogram_websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time spectrogram streaming."""
    await websocket.accept()
    await request.app.state.spectrogram_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await request.app.state.spectrogram_service.disconnect_websocket(websocket)
        logger.info("Spectrogram WebSocket client disconnected")
