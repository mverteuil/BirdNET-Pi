"""System API routes for hardware monitoring and system overview."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/hardware/status")
async def get_hardware_status() -> dict:
    """Get hardware monitoring status."""
    return SystemInspector.get_health_summary()


@router.get("/hardware/component/{component_name}")
async def get_hardware_component(component_name: str) -> dict:
    """Get specific hardware component status."""
    summary = SystemInspector.get_health_summary()

    if component_name not in summary["components"]:
        # Return unknown status for unrecognized components
        return {
            "component": component_name,
            "status": {
                "status": "unknown",
                "message": f"Component '{component_name}' not monitored",
            },
        }

    return {"component": component_name, "status": summary["components"][component_name]}


@router.get("/overview")
@inject
async def get_system_overview(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> dict:
    """Get system overview data including disk usage, system info, and total detections."""
    disk_usage = SystemInspector.get_disk_usage()
    system_info = SystemInspector.get_system_info()
    total_detections = data_manager.count_detections()

    return {
        "disk_usage": disk_usage,
        "system_info": system_info,
        "total_detections": total_detections,
    }
