"""API routes for progressive loading of analysis data."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/diversity")
@inject
async def get_diversity_analysis(
    period: str = Query("30d", description="Analysis period"),
    comparison: str | None = Query(None, description="Comparison period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get diversity metrics for the specified period."""
    try:
        # Calculate date ranges
        primary_dates = presentation_manager._calculate_analysis_period_dates(period)
        comparison_dates = (
            presentation_manager._calculate_analysis_period_dates(comparison)
            if comparison
            else None
        )

        # Get diversity data
        diversity_data = await presentation_manager.analytics_manager.calculate_diversity_timeline(
            start_date=primary_dates[0],
            end_date=primary_dates[1],
            temporal_resolution=presentation_manager._get_resolution_for_period(period),
        )

        result = {"diversity": presentation_manager._format_diversity_timeline(diversity_data)}

        # Add comparison if requested
        if comparison_dates:
            comparison_diversity = (
                await presentation_manager.analytics_manager.compare_period_diversity(
                    period1=primary_dates, period2=comparison_dates
                )
            )
            result["diversity_comparison"] = presentation_manager._format_diversity_comparison(
                comparison_diversity
            )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting diversity analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/accumulation")
@inject
async def get_accumulation_analysis(
    period: str = Query("30d", description="Analysis period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get species accumulation curve for the specified period."""
    try:
        primary_dates = presentation_manager._calculate_analysis_period_dates(period)

        accumulation_data = (
            await presentation_manager.analytics_manager.calculate_species_accumulation(
                start_date=primary_dates[0], end_date=primary_dates[1], method="collector"
            )
        )

        result = {
            "accumulation": presentation_manager._format_accumulation_curve(accumulation_data)
        }

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting accumulation analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/similarity")
@inject
async def get_similarity_analysis(
    period: str = Query("30d", description="Analysis period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get community similarity matrix for the specified period."""
    try:
        primary_dates = presentation_manager._calculate_analysis_period_dates(period)

        periods = presentation_manager._generate_similarity_periods(
            primary_dates[0], primary_dates[1]
        )
        similarity_data = (
            await presentation_manager.analytics_manager.calculate_community_similarity(
                periods=periods, index_type="jaccard"
            )
        )

        result = {"similarity": presentation_manager._format_similarity_matrix(similarity_data)}

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting similarity analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/beta")
@inject
async def get_beta_diversity(
    period: str = Query("30d", description="Analysis period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get beta diversity analysis for the specified period."""
    try:
        primary_dates = presentation_manager._calculate_analysis_period_dates(period)
        window_size = presentation_manager._get_window_size_for_period(period)

        beta_data = await presentation_manager.analytics_manager.calculate_beta_diversity(
            start_date=primary_dates[0], end_date=primary_dates[1], window_size=window_size
        )

        result = {"beta_diversity": presentation_manager._format_beta_diversity(beta_data)}

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting beta diversity: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/weather")
@inject
async def get_weather_correlations(
    period: str = Query("30d", description="Analysis period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get weather correlation analysis for the specified period."""
    try:
        primary_dates = presentation_manager._calculate_analysis_period_dates(period)

        weather_data = await presentation_manager.analytics_manager.get_weather_correlation_data(
            start_date=primary_dates[0], end_date=primary_dates[1]
        )

        result = {"weather": presentation_manager._format_weather_correlations(weather_data)}

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting weather correlations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/patterns")
@inject
async def get_temporal_patterns(
    period: str = Query("30d", description="Analysis period"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
) -> JSONResponse:
    """Get temporal pattern analysis for the specified period."""
    try:
        temporal = await presentation_manager.analytics_manager.get_temporal_patterns()
        heatmap = await presentation_manager.analytics_manager.get_aggregate_hourly_pattern(
            days=presentation_manager._get_days_for_period(period)
        )

        result = {
            "temporal_patterns": {
                "hourly": temporal["hourly_distribution"],
                "peak_hour": temporal["peak_hour"],
                "periods": temporal["periods"],
                "heatmap": heatmap,
            }
        }

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error getting temporal patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
