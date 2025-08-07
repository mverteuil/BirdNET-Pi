from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/overview")
@inject
async def get_overview_data(
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    hardware_monitor: HardwareMonitorService = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_service]
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
