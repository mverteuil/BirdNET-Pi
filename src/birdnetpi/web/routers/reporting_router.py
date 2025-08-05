import pandas as pd
import plotly.io as pio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.file_manager import FileManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.file_path_resolver import FilePathResolver

router = APIRouter()


def get_reporting_manager(request: Request) -> ReportingManager:
    """Return a ReportingManager instance with injected dependencies."""
    return ReportingManager(
        request.app.state.detections,
        request.app.state.file_resolver,
        request.app.state.config,
        request.app.state.plotting_manager,
        request.app.state.data_preparation_manager,
        request.app.state.location_service,
    )


def get_templates(request: Request) -> Jinja2Templates:
    """Return the templates instance."""
    return request.app.state.templates


def get_config(request: Request) -> BirdNETConfig:
    """Return the application config."""
    return request.app.state.config


def get_plotting_manager(request: Request) -> PlottingManager:
    """Return the plotting manager instance."""
    return request.app.state.plotting_manager


def get_file_manager(request: Request) -> FileManager:
    """Return a FileManager instance with injected dependencies."""
    file_resolver: FilePathResolver = request.app.state.file_resolver
    return FileManager(file_resolver.get_recordings_dir())


@router.get("/best", response_class=HTMLResponse)
async def get_best_recordings(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
    templates: Jinja2Templates = Depends(get_templates),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of the best recorded audio files based on confidence."""
    best_recordings = reporting_manager.get_best_detections(limit=20)
    return templates.TemplateResponse(
        request, "reports/best_recordings.html", {"best_recordings": best_recordings}
    )


@router.get("/detections")
async def get_detections(
    file_manager: FileManager = Depends(get_file_manager),  # noqa: B008
) -> dict:
    """Retrieve a list of all recorded audio files (detections)."""
    file_resolver = FilePathResolver()
    recordings_dir = file_resolver.get_recordings_dir()
    recordings = file_manager.list_directory_contents(recordings_dir)
    return {"recordings": recordings}


@router.get("/today", response_class=HTMLResponse)
async def get_todays_detections(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
    templates: Jinja2Templates = Depends(get_templates),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of today's detections."""
    todays_detections = reporting_manager.get_todays_detections()
    return templates.TemplateResponse(
        request,
        "reports/todays_detections.html",
        {"todays_detections": todays_detections},
    )


@router.get("/charts", response_class=HTMLResponse)
async def get_charts(
    request: Request,
    reporting_manager: ReportingManager = Depends(get_reporting_manager),  # noqa: B008
    plotting_manager: PlottingManager = Depends(get_plotting_manager),  # noqa: B008
    templates: Jinja2Templates = Depends(get_templates),  # noqa: B008
    config: BirdNETConfig = Depends(get_config),  # noqa: B008
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
