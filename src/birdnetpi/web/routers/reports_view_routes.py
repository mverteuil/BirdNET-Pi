"""Reports view routes for detection displays and analytics."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.system.status import SystemInspector
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/detections", response_class=HTMLResponse)
@router.get("/reports/detections", response_class=HTMLResponse)  # Keep for backward compatibility
@inject
async def get_all_detections(
    request: Request,
    period: str = Query("day", description="Time period to display"),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> HTMLResponse:
    """Render the detection display page with real-time data.

    The route simply wires together the presentation layer and template rendering.
    All data preparation is handled by PresentationManager.
    """
    try:
        # Get formatted data from PresentationManager
        template_data = await presentation_manager.get_detection_display_data(
            period=period,
            detection_query_service=detection_query_service,
        )

        # Add request context and site info
        template_data["request"] = request
        template_data["site_name"] = config.site_name
        template_data["system_status"] = {"device_name": SystemInspector.get_device_name()}

        # Render template with data
        return templates.TemplateResponse(
            name="reports/all_detections.html.j2",
            context=template_data,
        )

    except Exception as e:
        logger.error(f"Error rendering detection display page: {e}", exc_info=True)

        # Render with minimal fallback data
        return templates.TemplateResponse(
            name="reports/all_detections.html.j2",
            context={
                "request": request,
                "error": str(e),
                "location": "Unknown",
                "current_date": "Unknown",
                "species_count": 0,
                "recent_detections": [],
                "species_frequency": [],
                "top_species": [],
                "weekly_patterns": [],
                "sparkline_data": {},
                "week_patterns_data": {},
                "heatmap_data": [],
                "stem_leaf_data": [],
            },
        )
