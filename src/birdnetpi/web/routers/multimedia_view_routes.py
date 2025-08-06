"""Multimedia view routes for livestream and spectrogram HTML pages."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/livestream", response_class=HTMLResponse)
@inject
async def get_livestream(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
) -> HTMLResponse:
    """Render the livestream page."""
    return templates.TemplateResponse(request, "livestream.html", {})


@router.get("/spectrogram", response_class=HTMLResponse)
@inject
async def get_spectrogram(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
) -> HTMLResponse:
    """Render the spectrogram page."""
    return templates.TemplateResponse(request, "spectrogram.html", {})
