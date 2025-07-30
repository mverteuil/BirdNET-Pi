from unittest.mock import MagicMock  # Added for testing purposes

from fastapi import APIRouter, Depends, Request

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.managers.system_monitor import SystemMonitor
from birdnetpi.services.location_service import LocationService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

router = APIRouter()


def get_system_monitor() -> SystemMonitor:
    """Return a SystemMonitor instance."""
    return SystemMonitor()


def get_reporting_manager(request: Request) -> ReportingManager:
    """Return a ReportingManager instance with injected dependencies."""
    # TODO: Properly inject DetectionManager, FilePathResolver, and ConfigFileParser
    # These should ideally be initialized once in the lifespan and passed via app.state
    db_manager = DetectionManager(
        request.app.state.config.data.db_path
    )  # Assuming db_path is available in app.state.config.data
    file_path_resolver = FilePathResolver()
    config_parser = ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path())

    # Create specific mocks for the ReportingManager dependencies
    mock_plotting_manager = MagicMock(spec=PlottingManager)
    mock_data_preparation_manager = MagicMock(spec=DataPreparationManager)
    mock_location_service = MagicMock(spec=LocationService)

    return ReportingManager(
        db_manager,
        file_path_resolver,
        config_parser,
        mock_plotting_manager,
        mock_data_preparation_manager,
        mock_location_service,
    )


@router.get("/overview")
async def get_overview_data(
    system_monitor: SystemMonitor = Depends(get_system_monitor),  # noqa: B008
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
