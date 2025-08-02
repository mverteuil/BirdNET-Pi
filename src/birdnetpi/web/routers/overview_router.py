from fastapi import APIRouter, Depends, Request

from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.services.system_monitor_service import SystemMonitorService

router = APIRouter()


def get_system_monitor() -> SystemMonitorService:
    """Return a SystemMonitorService instance."""
    return SystemMonitorService()


def get_reporting_manager(request: Request) -> ReportingManager:
    """Return a ReportingManager instance with injected dependencies."""
    return ReportingManager(
        request.app.state.detections,
        request.app.state.file_path_resolver,
        request.app.state.config,
        request.app.state.plotting_manager,
        request.app.state.data_preparation_manager,
        request.app.state.location_service,
    )


@router.get("/overview")
async def get_overview_data(
    system_monitor: SystemMonitorService = Depends(get_system_monitor),  # noqa: B008
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> dict:
    """Retrieve various system and application overview data."""
    disk_usage = system_monitor.get_disk_usage()
    extra_info = system_monitor.get_extra_info()
    # You might want to add more data from reporting_manager here, e.g., total detections
    total_detections = reporting_manager.detection_manager.get_total_detections()

    return {
        "disk_usage": disk_usage,
        "extra_info": extra_info,
        "total_detections": total_detections,
    }
