from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.detections.data_manager import DataManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/overview")
@inject
async def get_overview_data(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> dict:
    """Retrieve various system and application overview data."""
    # Get system monitoring data using SystemInspector
    system_status = SystemInspector.get_health_summary()
    total_detections = data_manager.count_detections()

    return {
        "system_status": system_status,
        "total_detections": total_detections,
    }
