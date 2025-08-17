from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.managers.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/overview")
@inject
async def get_overview_data(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
) -> dict:
    """Retrieve various system and application overview data."""
    # Get system monitoring data from hardware monitor service
    system_status = hardware_monitor.get_all_status()
    total_detections = data_manager.count_detections()

    return {
        "system_status": system_status,
        "total_detections": total_detections,
    }
