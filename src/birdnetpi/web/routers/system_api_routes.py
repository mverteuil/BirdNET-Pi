"""System API routes for hardware monitoring and system overview."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException

from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.system_monitor_service import SystemMonitorService
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/hardware/status")
@inject
async def get_hardware_status(
    hardware_monitor: HardwareMonitorService = Depends(Provide[Container.hardware_monitor_service]),
) -> dict:
    """Get hardware monitoring status."""
    return hardware_monitor.get_all_status()


@router.get("/hardware/component/{component_name}")
@inject
async def get_hardware_component(
    component_name: str,
    hardware_monitor: HardwareMonitorService = Depends(Provide[Container.hardware_monitor_service]),
) -> dict:
    """Get specific hardware component status."""
    status = hardware_monitor.get_component_status(component_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")
    return {"component": component_name, "status": status}


@router.get("/overview")
@inject
async def get_system_overview(
    reporting_manager: ReportingManager = Depends(Provide[Container.reporting_manager]),
) -> dict:
    """Get system overview data including disk usage, system info, and total detections."""
    system_monitor = SystemMonitorService()
    disk_usage = system_monitor.get_disk_usage()
    extra_info = system_monitor.get_extra_info()
    total_detections = reporting_manager.detection_manager.get_total_detections()

    return {
        "disk_usage": disk_usage,
        "extra_info": extra_info,
        "total_detections": total_detections,
    }