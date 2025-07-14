from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.detection_event_publisher import DetectionEventPublisher
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver

from .routers import settings_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager for application startup and shutdown events."""
    # Load configuration
    config_parser = ConfigFileParser(FilePathResolver().get_birdnet_pi_config_path())
    app.state.config = config_parser.load_config()
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

app.include_router(settings_router.router)

templates = Jinja2Templates(directory="src/web/templates")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """Render the main index page."""
    return templates.TemplateResponse(
        request, "index.html", {"site_name": request.app.state.config.site_name}
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


@app.get("/test-detection")
async def test_detection() -> dict[str, str]:
    """Publishes a test detection event for demonstration purposes."""
    publisher.publish_detection({"species": "Test Bird", "confidence": 0.99})
    return {"message": "Test detection published"}
