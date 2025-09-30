"""System API routes for hardware monitoring and service management."""

import logging
import socket
import time
from dataclasses import asdict
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Path

from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.system.status import SystemInspector
from birdnetpi.system.system_control import SERVICES_CONFIG, SystemControlService
from birdnetpi.system.system_utils import SystemUtils
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.services import (
    ConfigReloadResponse,
    ServiceActionRequest,
    ServiceActionResponse,
    ServicesStatusResponse,
    ServiceStatus,
    SystemInfo,
    SystemRebootRequest,
    SystemRebootResponse,
    format_uptime,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/hardware/status")
@inject
async def get_hardware_status(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
) -> dict:
    """Get comprehensive hardware and system status.

    This endpoint provides all system metrics needed for monitoring,
    including health summary, detailed system info, and detection count.
    """
    # Get base health summary
    health_summary = SystemInspector.get_health_summary()

    # Get detailed system info
    system_info = SystemInspector.get_system_info()

    # Get total detections
    total_detections = await detection_query_service.count_detections()

    # Calculate uptime in days from boot time
    boot_time = system_info.get("boot_time", time.time())
    uptime_seconds = time.time() - boot_time
    uptime_days = int(uptime_seconds // 86400)

    # Combine all data for comprehensive status
    return {
        **health_summary,  # Include base health summary
        "system_info": {
            "device_name": system_info.get("device_name", "Unknown"),
            "platform": system_info.get("platform", "Unknown"),
            "cpu_count": system_info.get("cpu_count", 0),
            "uptime_days": uptime_days,
        },
        "resources": {
            "cpu": {
                "percent": system_info.get("cpu_percent", 0),
                "temperature": system_info.get("cpu_temperature"),
            },
            "memory": system_info.get("memory", {}),
            "disk": system_info.get("disk", {}),
        },
        "total_detections": total_detections,
    }


# Service configuration is now imported from system_control.py


@router.get("/services/status", response_model=ServicesStatusResponse)
@inject
async def get_services_status(
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> ServicesStatusResponse:
    """Get the status of all services and system information.

    Returns complete status information for all BirdNET-Pi services
    along with system uptime and reboot availability.
    """
    # Determine deployment type
    deployment_type = SystemUtils.get_deployment_environment()

    # Get appropriate service list
    service_configs = SERVICES_CONFIG.get(deployment_type, SERVICES_CONFIG["docker"])

    # Convert ServiceConfig to dict for system_control
    service_list = [asdict(config) for config in service_configs]

    # Get status for all services
    services_with_status = system_control.get_all_services_status(service_list)

    # Convert to ServiceStatus models
    service_statuses = []
    for service_info in services_with_status:
        # Add formatted uptime for each service if it has uptime_seconds
        if service_info.get("uptime_seconds") is not None:
            service_info["uptime_formatted"] = format_uptime(service_info["uptime_seconds"])
        service_statuses.append(ServiceStatus(**service_info))

    # Get system info
    system_info_data = system_control.get_system_info()

    # Add formatted uptime
    system_info_data["uptime_formatted"] = format_uptime(system_info_data["uptime_seconds"])
    system_info_data["deployment_type"] = deployment_type

    # Try to get hostname
    try:
        system_info_data["hostname"] = socket.gethostname()
    except Exception:
        system_info_data["hostname"] = None

    system_info = SystemInfo(**system_info_data)

    return ServicesStatusResponse(services=service_statuses, system=system_info)


@router.post("/services/reload-config", response_model=ConfigReloadResponse)
@inject
async def reload_configuration(
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> ConfigReloadResponse:
    """Reload service configuration without restarting services.

    Triggers a configuration reload for the service manager (systemd or supervisord).
    """
    try:
        system_control.daemon_reload()
        logger.info("Configuration reloaded successfully")
        return ConfigReloadResponse(
            success=True,
            message="Configuration reloaded successfully",
            services_affected=[],  # Could be enhanced to track affected services
        )
    except Exception as e:
        logger.exception("Failed to reload configuration")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/services/info", response_model=SystemInfo)
@inject
async def get_system_info(
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> SystemInfo:
    """Get system/container information including uptime."""
    system_info_data = system_control.get_system_info()

    # Add formatted uptime
    system_info_data["uptime_formatted"] = format_uptime(system_info_data["uptime_seconds"])
    system_info_data["deployment_type"] = SystemUtils.get_deployment_environment()

    # Try to get hostname
    try:
        system_info_data["hostname"] = socket.gethostname()
    except Exception:
        system_info_data["hostname"] = None

    return SystemInfo(**system_info_data)


@router.post("/services/reboot", response_model=SystemRebootResponse)
@inject
async def reboot_system(
    request: SystemRebootRequest,
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> SystemRebootResponse:
    """Reboot the system/container.

    Requires confirmation to prevent accidental reboots.
    Only available if the deployment supports it.
    """
    if not request.confirm:
        return SystemRebootResponse(
            success=False,
            message="Reboot requires confirmation",
            reboot_initiated=False,
        )

    if not system_control.can_reboot():
        return SystemRebootResponse(
            success=False,
            message="Reboot not available in this environment",
            reboot_initiated=False,
        )

    try:
        success = system_control.reboot_system()
        if success:
            logger.warning("System reboot initiated by user")
            return SystemRebootResponse(
                success=True,
                message="System reboot initiated. The system will restart shortly.",
                reboot_initiated=True,
            )
        else:
            return SystemRebootResponse(
                success=False,
                message="Failed to initiate reboot",
                reboot_initiated=False,
            )
    except Exception as e:
        logger.exception("Failed to reboot system")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/services")
@inject
async def get_services_list(
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> dict:
    """Get simplified list of available services for UI dropdowns.

    Returns a basic list of services for use in log filtering and other UI components.
    This is separate from the detailed status endpoint.

    Returns:
        Dictionary with service list and count
    """
    # Get deployment type to determine service names
    deployment_type = SystemUtils.get_deployment_environment()
    service_configs = SERVICES_CONFIG.get(deployment_type, SERVICES_CONFIG["docker"])

    # Convert to simple list format
    services = [
        {
            "name": config.name,
            "running": True,  # Will be dynamic in future
            "status": "running",  # Will be dynamic in future
        }
        for config in service_configs
    ]

    return {
        "services": services,
        "total": len(services),
    }


@router.post("/services/{service_name}/{action}", response_model=ServiceActionResponse)
@inject
async def perform_service_action(
    service_name: Annotated[str, Path(description="Name of the service")],
    action: Annotated[str, Path(pattern="^(start|stop|restart)$", description="Action to perform")],
    request: ServiceActionRequest,
    system_control: Annotated[
        SystemControlService, Depends(Provide[Container.system_control_service])
    ],
) -> ServiceActionResponse:
    """Perform an action on a service.

    Actions supported: start, stop, restart.
    Requires confirmation for critical services.
    """
    # Check if confirmation is required for critical services
    deployment_type = SystemUtils.get_deployment_environment()
    service_configs = SERVICES_CONFIG.get(deployment_type, SERVICES_CONFIG["docker"])
    service_config = next((s for s in service_configs if s.name == service_name), None)

    if service_config and service_config.critical and action in ["restart", "stop"]:
        if not request.confirm:
            return ServiceActionResponse(
                success=False,
                message=(
                    f"Action '{action}' on critical service '{service_name}' requires confirmation"
                ),
                service=service_name,
                action=action,
            )

    try:
        # Perform the action
        if action == "start":
            system_control.start_service(service_name)
        elif action == "stop":
            system_control.stop_service(service_name)
        elif action == "restart":
            system_control.restart_service(service_name)

        # Create proper past tense message
        action_messages = {
            "start": "started",
            "stop": "stopped",
            "restart": "restarted",
        }
        action_past = action_messages.get(action, f"{action}ed")

        logger.info(f"Service '{service_name}' {action_past} successfully")
        return ServiceActionResponse(
            success=True,
            message=f"Service '{service_name}' {action_past} successfully",
            service=service_name,
            action=action,
        )
    except Exception as e:
        logger.exception(f"Failed to {action} service '{service_name}'")
        return ServiceActionResponse(
            success=False,
            message=f"Failed to {action} service: {e!s}",
            service=service_name,
            action=action,
        )
