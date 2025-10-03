"""View routes for service status page."""

import logging
from dataclasses import asdict
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.system.system_control import SERVICES_CONFIG, SystemControlService
from birdnetpi.system.system_utils import SystemUtils
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.services import ServiceConfig, format_uptime
from birdnetpi.web.models.template_contexts import ServicesPageContext

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_services_with_status(
    system_control: SystemControlService | None, service_list: list[ServiceConfig]
) -> list[dict[str, Any]]:
    """Get services with their current status.

    Args:
        system_control: System control service instance
        service_list: List of service configurations

    Returns:
        List of services with status information
    """
    # Convert ServiceConfig objects to dicts
    services_as_dicts = [asdict(service) for service in service_list]

    if not system_control:
        return services_as_dicts

    try:
        return system_control.get_all_services_status(services_as_dicts)
    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        return services_as_dicts


def _format_service_for_display(service: dict[str, Any]) -> None:
    """Format service data for display by adding defaults and formatting uptime.

    Args:
        service: Service dictionary to format (modified in place)
    """
    # Ensure status field exists
    if "status" not in service:
        service["status"] = "unknown"

    # Format uptime
    if "uptime_seconds" in service and service["uptime_seconds"] is not None:
        service["uptime_formatted"] = format_uptime(service["uptime_seconds"])
    else:
        service["uptime_formatted"] = "N/A"

    # Ensure other fields have defaults
    service.setdefault("pid", None)
    service.setdefault("critical", False)
    service.setdefault("optional", False)


def _get_system_info(
    system_control: SystemControlService | None, deployment_type: str
) -> dict[str, Any]:
    """Get system information including uptime.

    Args:
        system_control: System control service instance
        deployment_type: Current deployment type

    Returns:
        Dictionary with system information
    """
    system_info: dict[str, Any] = {
        "uptime_seconds": 0,
        "reboot_available": False,
        "deployment_type": deployment_type,
    }

    if not system_control:
        system_info["uptime_formatted"] = "Unknown"
        return system_info

    try:
        updated_info = system_control.get_system_info()
        system_info.update(updated_info)
        system_info["uptime_formatted"] = format_uptime(system_info["uptime_seconds"])
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        system_info["uptime_formatted"] = "Unknown"

    return system_info


@router.get("/admin/services", response_class=HTMLResponse)
@inject
async def services_view(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    system_control: Annotated[
        SystemControlService | None, Depends(Provide[Container.system_control_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> HTMLResponse:
    """Render the services status page.

    Args:
        request: FastAPI request object
        templates: Jinja2 templates
        translation_manager: Translation manager for i18n
        system_control: System control service for getting service status
        config: BirdNET configuration

    Returns:
        Rendered HTML template
    """
    # Get user language for template
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

    # Determine deployment type
    deployment_type = SystemUtils.get_deployment_environment()

    # Get appropriate service list
    service_list = SERVICES_CONFIG.get(deployment_type, SERVICES_CONFIG["docker"])

    # Get services with status
    services_with_status = _get_services_with_status(system_control, service_list)

    # Format services for display
    for service in services_with_status:
        _format_service_for_display(service)

    # Get system information
    system_info = _get_system_info(system_control, deployment_type)

    # Create validated context
    context = ServicesPageContext(
        config=config,
        language=language,
        system_status={"device_name": SystemInspector.get_device_name()},
        page_name=_("Services"),
        active_page="services",
        model_update_date=None,
        services=services_with_status,
        system_info=system_info,
        deployment_type=deployment_type,
    )

    return templates.TemplateResponse(
        request,
        "admin/services.html.j2",
        context.model_dump(),
    )
