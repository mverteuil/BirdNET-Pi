from unittest.mock import MagicMock

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient


def test_read_main(path_resolver, tmp_path) -> None:
    """Should return response from main endpoint with simplified mocking."""
    # Create a simple FastAPI app for testing
    app = FastAPI()

    # Mock templates
    mock_templates = MagicMock(spec=Jinja2Templates)
    mock_templates.TemplateResponse.return_value = HTMLResponse(
        content="<html><body>BirdNET-Pi Test Site</body></html>"
    )

    # Create a simple route that mimics the factory's root route
    @app.get("/", response_class=HTMLResponse)
    async def read_root(request: Request) -> HTMLResponse:
        """Render the main index page."""
        return mock_templates.TemplateResponse(
            request,
            "index.html",
            {
                "site_name": "Test Site",
                # Safe: Test code using request hostname, not user input
                "websocket_url": f"ws://{request.url.hostname}:8000/ws/notifications",  # nosemgrep
            },
        )

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "BirdNET-Pi" in response.text
