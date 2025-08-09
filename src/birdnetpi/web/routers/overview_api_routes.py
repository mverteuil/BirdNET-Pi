from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.managers.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/overview")
@inject
async def get_overview_data(
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
) -> dict:
    """Retrieve various system and application overview data."""
    # Get system monitoring data from hardware monitor service
    system_status = hardware_monitor.get_all_status()
    total_detections = reporting_manager.detection_manager.get_total_detections()

    return {
        "system_status": system_status,
        "total_detections": total_detections,
    }
