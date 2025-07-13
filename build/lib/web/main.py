from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from models.birdnet_config import BirdNETConfig
from services.detection_event_publisher import DetectionEventPublisher
from utils.config_file_parser import ConfigFileParser

from .routers import settings_router

app = FastAPI()

app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

app.include_router(settings_router.router)

templates = Jinja2Templates(directory="src/web/templates")

# Load configuration
config_parser = ConfigFileParser("etc/birdnet_pi_config.yaml")
app_config: BirdNETConfig = config_parser.load_config()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"site_name": app_config.site_name}
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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
async def test_detection():
    publisher.publish_detection({"species": "Test Bird", "confidence": 0.99})
    return {"message": "Test detection published"}
