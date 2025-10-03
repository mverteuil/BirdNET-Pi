"""API routes for analysis data."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.analysis import AnalysisDataResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis")


@router.get("", response_model=AnalysisDataResponse)
@inject
async def get_analysis_data(
    presentation_manager: Annotated[
        PresentationManager, Depends(Provide[Container.presentation_manager])
    ],
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    comparison: str = Query("none", description="Comparison period"),
) -> AnalysisDataResponse:
    """Get analysis data for the specified date range.

    If start_date and end_date are not provided, defaults to last 30 days.
    """
    try:
        # Default to last 30 days if dates not provided
        if start_date is None or end_date is None:
            end = datetime.now(UTC).date()
            start = end - timedelta(days=30)
            start_date = start.isoformat()
            end_date = end.isoformat()

        # Map comparison value
        comparison_period = None if comparison == "none" else comparison

        # Get all data using date ranges
        data = await presentation_manager.get_analysis_page_data(
            start_date=start_date,
            end_date=end_date,
            comparison_period=comparison_period,
        )

        return AnalysisDataResponse(**data)

    except Exception as e:
        logger.error("Error getting analysis data: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
