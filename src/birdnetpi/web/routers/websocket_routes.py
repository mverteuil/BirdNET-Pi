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


@router.websocket("/audio")
async def audio_websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time audio streaming."""
    await websocket.accept()
    # Get the audio websocket service from the container
    audio_service = request.app.container.audio_websocket_service()
    await audio_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await audio_service.disconnect_websocket(websocket)
        logger.info("Audio WebSocket client disconnected")


@router.websocket("/spectrogram")
async def spectrogram_websocket_endpoint(websocket: WebSocket, request: Request) -> None:
    """Handle WebSocket connections for real-time spectrogram streaming."""
    await websocket.accept()
    # Get the spectrogram service from the container
    spectrogram_service = request.app.container.spectrogram_service()
    await spectrogram_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await spectrogram_service.disconnect_websocket(websocket)
        logger.info("Spectrogram WebSocket client disconnected")
