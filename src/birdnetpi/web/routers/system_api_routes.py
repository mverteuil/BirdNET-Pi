"""System API routes for hardware monitoring and system overview."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.managers.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.services.system_monitor_service import SystemMonitorService
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/hardware/status")
@inject
async def get_hardware_status(
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
) -> dict:
    """Get hardware monitoring status."""
    return hardware_monitor.get_all_status()


@router.get("/hardware/component/{component_name}")
@inject
async def get_hardware_component(
    component_name: str,
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
) -> dict:
    """Get specific hardware component status."""
    status = hardware_monitor.get_component_status(component_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")
    return {"component": component_name, "status": status}


@router.get("/overview")
@inject
async def get_system_overview(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> dict:
    """Get system overview data including disk usage, system info, and total detections."""
    system_monitor = SystemMonitorService()
    disk_usage = system_monitor.get_disk_usage()
    extra_info = system_monitor.get_extra_info()
    total_detections = data_manager.count_detections()

    return {
        "disk_usage": disk_usage,
        "extra_info": extra_info,
        "total_detections": total_detections,
    }
