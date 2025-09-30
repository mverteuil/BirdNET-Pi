"""Reports view routes for detection displays and analytics."""

import logging
from typing import Annotated

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
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    presentation_manager: Annotated[
        PresentationManager, Depends(Provide[Container.presentation_manager])
    ],
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    period: str = Query("day", description="Time period to display"),
) -> HTMLResponse:
    """Render the detection display page with real-time data.

    The route simply wires together the presentation layer and template rendering.
    All data preparation is handled by PresentationManager.
    """
    try:
        # Progressive loading: Don't fetch any data server-side
        # Just provide minimal context for the template
        template_data = {
            "request": request,
            "site_name": config.site_name,
            "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
            "system_status": {"device_name": SystemInspector.get_device_name()},
            "period": period,  # Pass the requested period for JavaScript to use
            # Empty data placeholders - JavaScript will populate these
            "current_date": "",
            "species_count": 0,
            "recent_detections": [],
            "species_frequency": [],
            "weekly_patterns": [],
        }

        # Render template with minimal data
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
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    period: str = Query("30d", description="Analysis period"),
    comparison: str = Query("none", description="Comparison period"),
) -> HTMLResponse:
    """Render the ecological analysis page shell for progressive loading."""
    # Just render the template shell - all data will be loaded via AJAX
    return templates.TemplateResponse(
        request,
        "reports/analysis.html.j2",
        {
            "request": request,
            "site_name": config.site_name,
            "location": f"{config.latitude:.4f}, {config.longitude:.4f}",
            "confidence_threshold": config.species_confidence_threshold,
            "period": period,
            "comparison_period": comparison if comparison != "none" else None,
            # Empty placeholders - JavaScript will fetch and populate
            "analyses": {},
            "summary": {},
            "generated_at": "",
        },
    )


@router.get("/reports/best", response_class=HTMLResponse)
@inject
async def get_best_recordings(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
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
