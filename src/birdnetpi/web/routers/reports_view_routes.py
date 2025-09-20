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
            request,
            "reports/all_detections.html.j2",
            template_data,
        )

    except Exception as e:
        logger.error(f"Error rendering detection display page: {e}", exc_info=True)

        # Render with minimal fallback data
        return templates.TemplateResponse(
            request,
            "reports/all_detections.html.j2",
            {
                "error": str(e),
                "location": "Unknown",
                "current_date": "Unknown",
                "species_count": 0,
                "recent_detections": [],
                "species_frequency": [],
                "weekly_patterns": [],
            },
        )


@router.get("/reports/analysis", response_class=HTMLResponse)
@inject
async def get_ecological_analysis(
    request: Request,
    period: str = Query("30d", description="Analysis period"),
    comparison: str = Query("none", description="Comparison period"),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> HTMLResponse:
    """Render the ecological analysis page with diversity metrics and visualizations."""
    try:
        # Map comparison value to PresentationManager format
        comparison_period = None if comparison == "none" else comparison

        # Get formatted data from PresentationManager
        # Set progressive=False to load all analytics data at once
        # With our weather query optimization, this should be fast now
        template_data = await presentation_manager.get_analysis_page_data(
            primary_period=period, comparison_period=comparison_period, progressive=False
        )

        # Add request context and site info
        template_data["request"] = request
        template_data["site_name"] = config.site_name
        template_data["location"] = f"{config.latitude:.4f}, {config.longitude:.4f}"
        template_data["confidence_threshold"] = config.species_confidence_threshold
        template_data["period"] = period
        template_data["comparison_period"] = comparison
        # Debug: Log the values being passed
        logger.info(f"Template variables: period={period}, comparison={comparison}")

        # Add current timestamp for the template
        import datetime

        template_data["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # Render template with data
        return templates.TemplateResponse(
            request,
            "reports/analysis.html.j2",
            template_data,
        )

    except Exception as e:
        logger.error(f"Error rendering ecological analysis page: {e}", exc_info=True)

        # Render with minimal fallback data
        import datetime

        return templates.TemplateResponse(
            request,
            "reports/analysis.html.j2",
            {
                "site_name": config.site_name,
                "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
                "confidence_threshold": config.species_confidence_threshold,
                "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "error": str(e),
                "analyses": {},
                "summary": {
                    "primary_period": {"start": "", "end": "", "total_detections": 0},
                },
            },
        )


@router.get("/reports/best", response_class=HTMLResponse)
@inject
async def get_best_recordings(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> HTMLResponse:
    """Render the best recordings page with high-confidence detections."""
    try:
        # Get high-confidence detections
        detections = await detection_query_service.query_detections(
            min_confidence=0.7,  # 70% confidence minimum
            limit=100,
            order_by="confidence",
            order_desc=True,
        )

        # Calculate statistics
        if detections:
            avg_confidence = sum(d.confidence for d in detections) / len(detections) * 100

            # Get date range
            dates = [d.timestamp for d in detections]
            date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"

            # Count unique species
            species = {d.scientific_name for d in detections}
            total_species = len(species)
        else:
            avg_confidence = 0
            date_range = "No detections"
            total_species = 0

        # Prepare template data
        template_data = {
            "request": request,
            "site_name": config.site_name,
            "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
            "detections": detections,
            "avg_confidence": avg_confidence,
            "date_range": date_range,
            "total_species": total_species,
        }

        # Render template
        return templates.TemplateResponse(
            request,
            "reports/best_recordings.html.j2",
            template_data,
        )

    except Exception as e:
        logger.error(f"Error rendering best recordings page: {e}", exc_info=True)

        # Render with error
        return templates.TemplateResponse(
            request,
            "reports/best_recordings.html.j2",
            {
                "site_name": config.site_name,
                "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
                "detections": [],
                "avg_confidence": 0,
                "date_range": "Error loading data",
                "total_species": 0,
                "error": str(e),
            },
        )
