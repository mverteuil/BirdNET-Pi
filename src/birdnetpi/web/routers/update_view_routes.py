"""Update view routes for system update management UI."""

import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@inject
async def update_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> HTMLResponse:
    """Render the system update page.

    This page provides:
    - Current version information
    - Available update details
    - Update history
    - Real-time update progress via SSE
    """
    # Get current update status from cache
    update_status = cache.get("update:status") or {}

    # Get last update result if any
    update_result = cache.get("update:result") or {}

    # Render the update template
    return templates.TemplateResponse(
        request,
        "admin/update.html.j2",
        {
            "title": "System Updates",
            "update_status": update_status,
            "update_result": update_result,
            "sse_endpoint": "/api/update/stream",
            "active_page": "update",  # Set active page for navigation
            "latitude": config.latitude,
            "longitude": config.longitude,
            "git_remote": config.updates.git_remote,
            "git_branch": config.updates.git_branch,
        },
    )
