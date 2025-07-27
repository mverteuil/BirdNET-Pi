import datetime
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
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager
from birdnetpi.services.location_service import LocationService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.utils.logging_configurator import configure_logging  # Added import

from .routers import (
    audio_router,
    log_router,
    overview_router,
    reporting_router,
    settings_router,
    spectrogram_router,
)


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

    yield


app = FastAPI(lifespan=lifespan)

app.include_router(settings_router.router)
app.include_router(log_router.router)
app.include_router(audio_router.router)
app.include_router(reporting_router.router)
app.include_router(spectrogram_router.router)

app.include_router(overview_router.router)


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
    try:
        while True:
            # This example just keeps the connection open. Real-time updates
            # would be pushed from the DetectionEventPublisher.
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("Client disconnected")


# Example of how to use the publisher (for testing/demonstration)
# In a real scenario, this would be triggered by actual detection events.
publisher = DetectionEventPublisher()


@app.get("/test_detection_form", response_class=HTMLResponse)
async def test_detection_form(request: Request) -> HTMLResponse:
    """Render the form for testing detections."""
    return request.app.state.templates.TemplateResponse(request, "test_detection_modal.html", {})


@app.get("/test_detection")
async def test_detection(
    species: str = "Test Bird",
    confidence: float = 0.99,
    timestamp: str | None = None,
) -> dict[str, str]:
    """Publishes a test detection event for demonstration purposes."""
    detection_data = {
        "species": species,
        "confidence": confidence,
        "timestamp": timestamp if timestamp else datetime.datetime.now().isoformat(),
    }
    publisher.publish_detection(detection_data)
    return {"message": "Test detection published", "data": detection_data}
