"""Multimedia view routes for livestream HTML pages."""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.utils.auth import require_admin
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.template_contexts import LivestreamPageContext

router = APIRouter()


@router.get("/livestream", response_class=HTMLResponse)
@require_admin
@inject
async def get_livestream(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> HTMLResponse:
    """Render the livestream page."""
    # Get user language for template
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

    # Create validated context
    context = LivestreamPageContext(
        config=config,
        language=language,
        system_status={"device_name": SystemInspector.get_device_name()},
        page_name=_("Audio Stream"),
        active_page="livestream",
        model_update_date=None,
    )

    return templates.TemplateResponse(
        request,
        "admin/livestream.html.j2",
        context.model_dump(),
    )
