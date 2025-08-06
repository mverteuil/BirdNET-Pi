"""Field mode view routes for rendering HTML interfaces."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/field", response_class=HTMLResponse)
@inject
async def get_field_mode(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
    config: BirdNETConfig = Depends(Provide[Container.config]),
) -> HTMLResponse:
    """Render the field mode interface."""
    return templates.TemplateResponse(request, "field_mode.html", {"site_name": config.site_name})
