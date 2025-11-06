"""View routes for log viewing interface."""

import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.system.system_control import SERVICES_CONFIG, SystemControlService
from birdnetpi.system.system_utils import SystemUtils
from birdnetpi.utils.auth import require_admin
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.logs import LOG_LEVELS
from birdnetpi.web.models.template_contexts import LogsPageContext

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs", response_class=HTMLResponse)
@require_admin
@inject
async def view_logs(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> Response:
    """Render the log viewer page.

    Args:
        request: FastAPI request object
        templates: Jinja2 templates
        translation_manager: Translation manager for i18n
        system_control: System control service for getting service list
        config: BirdNET configuration

    Returns:
        Rendered HTML template
    """
    # Get user language for template
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

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

    # Create validated context
    context = LogsPageContext(
        config=config,
        language=language,
        system_status={"device_name": SystemInspector.get_device_name()},
        page_name=_("Logs"),
        active_page="logs",
        model_update_date=None,
        services=services,
        log_levels=LOG_LEVELS,
    )

    return templates.TemplateResponse(
        request,
        "admin/logs.html.j2",
        context.model_dump(),
    )
