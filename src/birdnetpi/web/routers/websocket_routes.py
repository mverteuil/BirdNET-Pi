"""WebSocket routes for real-time communication."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from birdnetpi.services.audio_websocket_service import AudioWebSocketService
from birdnetpi.services.spectrogram_service import SpectrogramService
from birdnetpi.web.core.container import Container

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
@inject
async def audio_websocket_endpoint(
    websocket: WebSocket,
    audio_service: AudioWebSocketService = Depends(Provide[Container.audio_websocket_service])
) -> None:
    """Handle WebSocket connections for real-time audio streaming."""
    await websocket.accept()
    await audio_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await audio_service.disconnect_websocket(websocket)
        logger.info("Audio WebSocket client disconnected")


@router.websocket("/spectrogram")
@inject
async def spectrogram_websocket_endpoint(
    websocket: WebSocket,
    spectrogram_service: SpectrogramService = Depends(Provide[Container.spectrogram_service])
) -> None:
    """Handle WebSocket connections for real-time spectrogram streaming."""
    await websocket.accept()
    await spectrogram_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await spectrogram_service.disconnect_websocket(websocket)
        logger.info("Spectrogram WebSocket client disconnected")
