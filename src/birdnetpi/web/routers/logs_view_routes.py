"""View routes for log viewing interface."""

import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.system.system_control import SERVICES_CONFIG, SystemControlService
from birdnetpi.system.system_utils import SystemUtils
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs", response_class=HTMLResponse)
@inject
async def view_logs(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
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
    # Get services from centralized configuration
    deployment_type = SystemUtils.get_deployment_environment()
    service_configs = SERVICES_CONFIG.get(deployment_type, SERVICES_CONFIG["docker"])

    # Convert to format expected by template
    services = [{"name": service.name, "running": True} for service in service_configs]

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
