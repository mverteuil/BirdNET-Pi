import pandas as pd
import plotly.io as pio
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


@router.get("/reports/charts", response_class=HTMLResponse)
async def get_charts(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
) -> HTMLResponse:
    """Generate and display various charts related to bird detections."""
    # Get plotting manager from app state
    plotting_manager = request.app.state.plotting_manager
    df = reporting_manager.get_data()

    # Default values for plot generation
    start_date = (
        pd.to_datetime(df.index.min()).date() if not df.empty else pd.Timestamp.now().date()
    )
    end_date = pd.to_datetime(df.index.max()).date() if not df.empty else pd.Timestamp.now().date()
    top_n = 10

    specie = "All"
    num_days_to_display = getattr(
        request.app.state.config, "num_days_to_display", 7
    )  # Default to 7 days
    selected_pal = "Viridis"  # Arbitrary for now

    # Generate multi-day plot
    multi_day_fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
        df, "Hourly", start_date, end_date, top_n, specie
    )
    multi_day_plot_json = pio.to_json(multi_day_fig)

    # Generate daily plot
    # Handle empty DataFrame case for species selection
    most_common_species = (
        df["Com_Name"].mode()[0] if not df.empty and len(df["Com_Name"].mode()) > 0 else "All"
    )
    daily_fig = plotting_manager.generate_daily_detections_plot(
        df,
        "15 minutes",
        start_date,
        most_common_species,
        num_days_to_display,
        selected_pal,
    )
    daily_plot_json = pio.to_json(daily_fig)

    plot_data = {"multi_day_plot": multi_day_plot_json, "daily_plot": daily_plot_json}

    return request.app.state.templates.TemplateResponse(
        request, "charts.html", {"plot_data": plot_data}
    )
