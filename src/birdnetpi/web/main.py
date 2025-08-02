import datetime
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqladmin import Admin, ModelView

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.service_manager import ServiceManager
from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.audio_fifo_reader_service import AudioFifoReaderService
from birdnetpi.services.audio_websocket_service import AudioWebSocketService
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.file_manager import FileManager
from birdnetpi.services.location_service import LocationService
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.services.spectrogram_service import SpectrogramService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.utils.logging_configurator import configure_logging
from birdnetpi.web.routers.api_router import DetectionEvent

from .routers import (
    api_router,
    audio_router,
    log_router,
    overview_router,
    reporting_router,
    settings_router,
    spectrogram_router,
    views_router,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager for application startup and shutdown events."""
    # Load configuration
    app.state.file_resolver = FilePathResolver()
    config_parser = ConfigFileParser(app.state.file_resolver.get_birdnet_pi_config_path())
    app.state.config = config_parser.load_config()
    app.mount(
        "/static",
        StaticFiles(directory=app.state.file_resolver.get_static_dir()),
        name="static",
    )

    # Initialize Jinja2Templates and store it in app.state
    app.state.templates = Jinja2Templates(directory=app.state.file_resolver.get_templates_dir())

    # Configure logging based on loaded config
    configure_logging(app.state.config)  # Added logging configuration

    # Initialize core services and managers
    app.state.db_service = DatabaseService(app.state.config.data.db_path)
    app.state.file_manager = FileManager(app.state.file_resolver.base_dir)
    app.state.detections = DetectionManager(app.state.db_service)
    app.state.location_service = LocationService(
        app.state.config.latitude, app.state.config.longitude
    )
    app.state.data_preparation_manager = DataPreparationManager(
        app.state.config, app.state.location_service
    )
    app.state.plotting_manager = PlottingManager(app.state.data_preparation_manager)
    app.state.service_manager = ServiceManager()
    app.state.active_websockets = set()  # Initialize set for active WebSocket connections
    app.state.audio_websocket_service = AudioWebSocketService(
        samplerate=app.state.config.sample_rate, channels=app.state.config.audio_channels
    )
    app.state.spectrogram_service = SpectrogramService(
        sample_rate=app.state.config.sample_rate,
        channels=app.state.config.audio_channels,
        window_size=1024,  # Good balance of frequency/time resolution
        overlap=0.75,  # High overlap for smooth visualization
        update_rate=15.0,  # 15 FPS for smooth real-time display
    )

    # Initialize and start the FIFO reader service for WebSocket streaming
    fifo_base_path = app.state.file_resolver.get_fifo_base_path()
    livestream_fifo_path = f"{fifo_base_path}/birdnet_audio_livestream.fifo"
    app.state.audio_fifo_reader_service = AudioFifoReaderService(
        livestream_fifo_path, app.state.audio_websocket_service, app.state.spectrogram_service
    )

    # Initialize NotificationService and register listeners
    app.state.notification_service = NotificationService(
        app.state.active_websockets, app.state.config
    )
    app.state.notification_service.register_listeners()

    # Initialize SQLAdmin
    admin = Admin(app, app.state.db_service.engine)
    app.mount("/admin", admin.app, name="sqladmin")

    class DetectionAdmin(ModelView, model=Detection):
        column_list: ClassVar[list] = [
            Detection.id,
            Detection.species,
            Detection.confidence,
            Detection.timestamp,
        ]
        # Add other configurations as needed

    class AudioFileAdmin(ModelView, model=AudioFile):
        column_list: ClassVar[list] = [
            AudioFile.id,
            AudioFile.file_path,
            AudioFile.duration,
            AudioFile.recording_start_time,
        ]
        # Add other configurations as needed

    admin.add_view(DetectionAdmin)
    admin.add_view(AudioFileAdmin)

    # Start the FIFO reader service
    await app.state.audio_fifo_reader_service.start()

    yield

    # Cleanup: Stop the FIFO reader service
    await app.state.audio_fifo_reader_service.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(settings_router.router)
app.include_router(log_router.router)
app.include_router(audio_router.router)
app.include_router(reporting_router.router)
app.include_router(spectrogram_router.router)
app.include_router(views_router.router)

app.include_router(overview_router.router)
app.include_router(api_router.router, prefix="/api")  # Include the new API router


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """Render the main index page."""
    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {
            "site_name": request.app.state.config.site_name,
            "websocket_url": f"ws://{request.url.hostname}:8000/ws",
        },
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time updates."""
    await websocket.accept()
    app.state.active_websockets.add(websocket)  # Add new connection
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        app.state.active_websockets.remove(websocket)  # Remove disconnected client
        logger.info("Client disconnected")


@app.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time audio streaming."""
    await websocket.accept()
    await app.state.audio_websocket_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await app.state.audio_websocket_service.disconnect_websocket(websocket)
        logger.info("Audio WebSocket client disconnected")


@app.websocket("/ws/spectrogram")
async def spectrogram_websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time spectrogram streaming."""
    await websocket.accept()
    await app.state.spectrogram_service.connect_websocket(websocket)
    try:
        while True:
            # Keep the connection alive by receiving ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await app.state.spectrogram_service.disconnect_websocket(websocket)
        logger.info("Spectrogram WebSocket client disconnected")


@app.get("/test_detection_form", response_class=HTMLResponse)
async def test_detection_form(request: Request) -> HTMLResponse:
    """Render the form for testing detections."""
    return request.app.state.templates.TemplateResponse(request, "test_detection_modal.html", {})


@app.get("/test_detection")
async def test_detection(
    species: str = "Test Bird",
    confidence: float = 0.99,
    timestamp: str | None = None,
    file_path: str = "test_audio/test_bird.wav",
    duration: float = 3.0,
    size_bytes: int = 1024,
    recording_start_time: str | None = None,
    latitude: float = 0.0,
    longitude: float = 0.0,
    cutoff: float = 0.0,
    week: int = 0,
    sensitivity: float = 0.0,
    overlap: float = 0.0,
) -> dict[str, str]:
    """Publishes a test detection event for demonstration purposes."""
    detection_event_data = DetectionEvent(
        species=species,
        confidence=confidence,
        timestamp=datetime.datetime.fromisoformat(timestamp)
        if timestamp
        else datetime.datetime.now(),
        file_path=file_path,
        duration=duration,
        size_bytes=size_bytes,
        recording_start_time=datetime.datetime.fromisoformat(recording_start_time)
        if recording_start_time
        else datetime.datetime.now(),
        latitude=latitude,
        longitude=longitude,
        cutoff=cutoff,
        week=week,
        sensitivity=sensitivity,
        overlap=overlap,
    )
    app.state.detections.create_detection(detection_event_data)
    return {"message": "Test detection published", "data": detection_event_data.model_dump_json()}
