import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqladmin import Admin, ModelView
from sqlalchemy import create_engine

from birdnetpi.managers.service_manager import ServiceManager
from birdnetpi.models.database_models import AudioFile, Base, Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

from .routers import (
    log_router,
    overview_router,
    recordings_router,
    reporting_router,
    settings_router,
    spectrogram_router,
    todays_detections_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager for application startup and shutdown events."""
    # Load configuration
    config_parser = ConfigFileParser(FilePathResolver().get_birdnet_pi_config_path())
    app.state.config = config_parser.load_config()

    # Initialize SQLAlchemy engine and SQLAdmin
    engine = create_engine(f"sqlite:///{app.state.config.data.db_path}")
    Base.metadata.create_all(engine)  # Create tables
    admin = Admin(app, engine)
    app.mount("/admin", admin.app, name="sqladmin")

    # Initialize core services and managers
    app.state.file_manager = FileManager(FilePathResolver().repo_root)
    app.state.db_service = DatabaseService(app.state.config.data.db_path)
    app.state.service_manager = ServiceManager(app.state.config)

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

app.mount(
    "/static", StaticFiles(directory="/app/src/birdnetpi/web/static"), name="static"
)

app.include_router(settings_router.router)
app.include_router(log_router.router)
app.include_router(recordings_router.router)
app.include_router(reporting_router.router)
app.include_router(spectrogram_router.router)
app.include_router(todays_detections_router.router)
app.include_router(overview_router.router)

templates = Jinja2Templates(directory="/app/src/birdnetpi/web/templates")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """Render the main index page."""
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(request, "test_detection_modal.html", {})


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
