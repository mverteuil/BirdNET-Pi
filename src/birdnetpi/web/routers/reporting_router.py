from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from birdnetpi.managers.reporting_manager import ReportingManager

router = APIRouter()


def get_reporting_manager(request: Request) -> ReportingManager:
    """Return a ReportingManager instance with injected dependencies."""
    detection_manager = request.app.state.detections
    file_path_resolver = request.app.state.file_resolver
    config = request.app.state.config
    plotting_manager = request.app.state.plotting_manager
    data_preparation_manager = request.app.state.data_preparation_manager
    location_service = request.app.state.location_service

    return ReportingManager(
        detection_manager,
        file_path_resolver,
        config,
        plotting_manager,
        data_preparation_manager,
        location_service,
    )


@router.get("/best_recordings", response_class=HTMLResponse)
async def get_best_recordings(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of the best recorded audio files based on confidence."""
    best_recordings = reporting_manager.get_best_detections(limit=20)
    return request.app.state.templates.TemplateResponse(
        request, "reports/best_recordings.html", {"best_recordings": best_recordings}
    )


@router.get("/reports/todays_detections", response_class=HTMLResponse)
async def get_todays_detections(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of today's detections."""
    todays_detections = reporting_manager.get_todays_detections()
    return request.app.state.templates.TemplateResponse(
        request,
        "reports/todays_detections.html",
        {"todays_detections": todays_detections},
    )
