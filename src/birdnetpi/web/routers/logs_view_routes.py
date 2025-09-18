"""View routes for log viewing interface."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs", response_class=HTMLResponse)
@inject
async def view_logs(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    system_control: SystemControlService = Depends(  # noqa: B008
        Provide[Container.system_control_service]
    ),
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> Response:
    """Render the log viewer page.

    Args:
        request: FastAPI request object
        templates: Jinja2 templates
        system_control: System control service for getting service list
        config: BirdNET configuration

    Returns:
        Rendered HTML template
    """
    # Define known BirdNET-Pi services
    # In production, these would be discovered from supervisorctl or systemd
    services = [
        {"name": "fastapi", "running": True},
        {"name": "audio_capture", "running": True},
        {"name": "audio_analysis", "running": True},
        {"name": "audio_websocket", "running": True},
        {"name": "caddy", "running": True},
        {"name": "memcached", "running": True},
    ]

    # In the future, we could check actual status for each service
    # for service in services:
    #     try:
    #         status = system_control.get_service_status(service["name"])
    #         service["running"] = "running" in status.lower()
    #     except Exception:
    #         pass

    return templates.TemplateResponse(
        request,
        "admin/logs.html.j2",
        {
            "services": services,
            "log_levels": LOG_LEVELS,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "active_page": "logs",  # Set active page for navigation
        },
    )
