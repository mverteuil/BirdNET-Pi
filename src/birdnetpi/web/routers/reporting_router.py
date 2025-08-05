import pandas as pd
import plotly.io as pio
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.file_manager import FileManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.models.config import BirdNETConfig
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/best", response_class=HTMLResponse)
@inject
async def get_best_recordings(
    request: Request,
    reporting_manager: ReportingManager = Depends(Provide[Container.reporting_manager]),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
) -> HTMLResponse:
    """Retrieve a list of the best recorded audio files based on confidence."""
    best_recordings = reporting_manager.get_best_detections(limit=20)
    return templates.TemplateResponse(
        request, "reports/best_recordings.html", {"best_recordings": best_recordings}
    )


@router.get("/detections")
@inject
async def get_detections(
    file_manager: FileManager = Depends(Provide[Container.file_manager]),
) -> dict:
    """Retrieve a list of all recorded audio files (detections)."""
    recordings = file_manager.list_directory_contents()
    return {"recordings": recordings}


@router.get("/today", response_class=HTMLResponse)
@inject
async def get_todays_detections(
    request: Request,
    reporting_manager: ReportingManager = Depends(Provide[Container.reporting_manager]),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
) -> HTMLResponse:
    """Retrieve a list of today's detections."""
    todays_detections = reporting_manager.get_todays_detections()
    return templates.TemplateResponse(
        request,
        "reports/todays_detections.html",
        {"todays_detections": todays_detections},
    )


@router.get("/charts", response_class=HTMLResponse)
@inject
async def get_charts(
    request: Request,
    reporting_manager: ReportingManager = Depends(Provide[Container.reporting_manager]),
    plotting_manager: PlottingManager = Depends(Provide[Container.plotting_manager]),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),
    config: BirdNETConfig = Depends(Provide[Container.config]),
) -> HTMLResponse:
    """Generate and display various charts related to bird detections."""
    df = reporting_manager.get_data()

    # Default values for plot generation
    start_date = (
        pd.to_datetime(str(df.index.min())).date() if not df.empty else pd.Timestamp.now().date()
    )
    end_date = (
        pd.to_datetime(str(df.index.max())).date() if not df.empty else pd.Timestamp.now().date()
    )
    top_n = 10

    species = "All"
    num_days_to_display = getattr(config, "num_days_to_display", 7)  # Default to 7 days
    selected_pal = "Viridis"  # Arbitrary for now

    # Generate multi-day plot
    multi_day_fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
        df, "Hourly", str(start_date), str(end_date), top_n, species
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
        str(start_date),
        str(most_common_species),
        num_days_to_display,
        selected_pal,
    )
    daily_plot_json = pio.to_json(daily_fig)

    plot_data = {"multi_day_plot": multi_day_plot_json, "daily_plot": daily_plot_json}

    return templates.TemplateResponse(request, "charts.html", {"plot_data": plot_data})
