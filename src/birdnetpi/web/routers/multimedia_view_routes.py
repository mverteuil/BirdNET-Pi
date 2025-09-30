"""Multimedia view routes for livestream HTML pages."""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/livestream", response_class=HTMLResponse)
@inject
async def get_livestream(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> HTMLResponse:
    """Render the livestream page."""
    return templates.TemplateResponse(
        request, "admin/livestream.html.j2", {"site_name": config.site_name}
    )
