from fastapi import APIRouter, Depends, Request

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver

router = APIRouter()


def get_reporting_manager(request: Request) -> ReportingManager:
    """Return a ReportingManager instance with injected dependencies."""
    # TODO: Properly inject DetectionManager, FilePathResolver, and ConfigFileParser
    # These should ideally be initialized once in the lifespan and passed via app.state
    db_manager = DetectionManager(
        request.app.state.config.data.db_path
    )  # Assuming db_path is available in app.state.config.data
    file_path_resolver = FilePathResolver(
        request.app.state.file_resolver.repo_root
    )  # Assuming repo_root is available in app.state
    config_parser = ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path())
    return ReportingManager(db_manager, file_path_resolver, config_parser)


@router.get("/todays_detections")
async def get_todays_detections(
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of today's detections."""
    todays_detections = reporting_manager.get_todays_detections()
    return {"todays_detections": todays_detections}
