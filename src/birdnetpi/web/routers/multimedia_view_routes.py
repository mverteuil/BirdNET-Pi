"""Multimedia view routes for livestream HTML pages."""

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
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> HTMLResponse:
    """Render the livestream page."""
    return templates.TemplateResponse(request, "livestream.html", {"site_name": config.site_name})
