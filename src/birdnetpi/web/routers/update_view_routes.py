"""Update view routes for system update management UI."""

import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.utils.cache import Cache
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.template_contexts import UpdatePageContext
from birdnetpi.web.models.update import UpdateActionResponse, UpdateStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@inject
async def update_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
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
    # Get user language for template
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

    # Get current update status from cache
    cached_status = cache.get("update:status")
    if cached_status and isinstance(cached_status, dict):
        try:
            update_status = UpdateStatusResponse(**cached_status)
        except Exception as e:
            logger.warning(f"Failed to parse cached update status: {e}")
            update_status = UpdateStatusResponse(available=False)
    elif isinstance(cached_status, UpdateStatusResponse):
        update_status = cached_status
    else:
        # Default: no update available
        update_status = UpdateStatusResponse(available=False)

    # Get last update result if any
    cached_result = cache.get("update:result")
    if cached_result and isinstance(cached_result, dict):
        try:
            update_result = UpdateActionResponse(**cached_result)
        except Exception as e:
            logger.warning(f"Failed to parse cached update result: {e}")
            update_result = None
    elif isinstance(cached_result, UpdateActionResponse):
        update_result = cached_result
    else:
        update_result = None

    # Create validated context
    context = UpdatePageContext(
        config=config,
        language=language,
        system_status={"device_name": SystemInspector.get_device_name()},
        page_name=_("System Updates"),
        active_page="update",
        model_update_date=None,
        title=_("System Updates"),
        update_status=update_status,
        update_result=update_result,
        sse_endpoint="/api/update/stream",
        git_remote=config.updates.git_remote,
        git_branch=config.updates.git_branch,
    )

    # Render the update template
    return templates.TemplateResponse(
        request,
        "admin/update.html.j2",
        context.model_dump(),
    )
