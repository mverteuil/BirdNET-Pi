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
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.system.status import SystemInspector
from birdnetpi.utils.language import get_user_language
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.template_contexts import (
    AnalysisPageContext,
    BestRecordingsPageContext,
    DetectionsPageContext,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/detections", response_class=HTMLResponse)
@inject
async def detections_view(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    presentation_manager: Annotated[
        PresentationManager, Depends(Provide[Container.presentation_manager])
    ],
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    period: str = Query("day", description="Time period to display"),
) -> HTMLResponse:
    """Render the detection display page with real-time data.

    The route simply wires together the presentation layer and template rendering.
    All data preparation is handled by PresentationManager.
    """
    try:
        # Get user language and translate page name
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        # Progressive loading: Don't fetch any data server-side
        # Build validated context using Pydantic model
        context = DetectionsPageContext(
            config=config,
            system_status={"device_name": SystemInspector.get_device_name()},
            language=language,
            active_page="detections",
            page_name=_("Detections"),
            period=period,
        )

        # Render template with validated context
        return templates.TemplateResponse(
            request,
            "reports/all_detections.html.j2",
            context.model_dump(),
        )

    except Exception as e:
        logger.error(f"Error rendering detection display page: {e}", exc_info=True)

        # Get user language for error context
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        # Render with error context
        error_context = DetectionsPageContext(
            config=config,
            system_status={"device_name": SystemInspector.get_device_name()},
            language=language,
            active_page="detections",
            page_name=_("Detections"),
            period=period,
            error=str(e),
        )

        return templates.TemplateResponse(
            request,
            "reports/all_detections.html.j2",
            error_context.model_dump(),
        )


@router.get("/reports/analysis", response_class=HTMLResponse)
@inject
async def analysis_view(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    period: str = Query("month", description="Analysis period"),
    comparison: str = Query("none", description="Comparison period"),
) -> HTMLResponse:
    """Render the ecological analysis page shell for progressive loading."""
    # Get user language and translate page name
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

    # Build validated context using Pydantic model
    context = AnalysisPageContext(
        config=config,
        system_status={"device_name": SystemInspector.get_device_name()},
        language=language,
        active_page="analysis",
        page_name=_("Analysis"),
        period=period,
        comparison_period=comparison if comparison != "none" else None,
    )

    return templates.TemplateResponse(
        request,
        "reports/analysis.html.j2",
        context.model_dump(),
    )


@router.get("/reports/best", response_class=HTMLResponse)
@inject
async def best_recordings_view(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(Provide[Container.templates])],
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
) -> HTMLResponse:
    """Render the best recordings page with high-confidence detections."""
    # Get user language and translator
    language = get_user_language(request, config)
    _ = translation_manager.get_translation(language).gettext

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

        # Build validated context using Pydantic model
        context = BestRecordingsPageContext(
            config=config,
            system_status={"device_name": SystemInspector.get_device_name()},
            language=language,
            active_page="best",
            page_name=_("Best Recordings"),
            detections=detections,
            avg_confidence=avg_confidence,
            date_range=date_range,
            total_species=total_species,
        )

        # Render template
        return templates.TemplateResponse(
            request,
            "reports/best_recordings.html.j2",
            context.model_dump(),
        )

    except Exception as e:
        logger.error(f"Error rendering best recordings page: {e}", exc_info=True)

        # Get user language for error context
        language = get_user_language(request, config)
        _ = translation_manager.get_translation(language).gettext

        # Render with error context
        error_context = BestRecordingsPageContext(
            config=config,
            system_status={"device_name": SystemInspector.get_device_name()},
            language=language,
            active_page="best",
            page_name=_("Best Recordings"),
            detections=[],
            avg_confidence=0.0,
            date_range="Error loading data",
            total_species=0,
            error=str(e),
        )

        return templates.TemplateResponse(
            request,
            "reports/best_recordings.html.j2",
            error_context.model_dump(),
        )
