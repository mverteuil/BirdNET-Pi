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
        request.app.state.repo_root
    )  # Assuming repo_root is available in app.state
    config_parser = ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path())
    return ReportingManager(db_manager, file_path_resolver, config_parser)


@router.get("/best_recordings")
async def get_best_recordings(
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of the best recorded audio files based on confidence."""
    # TODO: Assuming 'best' means highest confidence, you might want to add a confidence threshold
    # or sort by confidence in get_most_recent_detections if it doesn't already.
    best_recordings = reporting_manager.get_most_recent_detections(
        limit=20
    )  # Adjust limit as needed
    return {"best_recordings": best_recordings}
