import pandas as pd
import plotly.io as pio
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@inject
async def get_reports_index(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Render the reports index page with navigation to different reports."""
    return templates.TemplateResponse(request, "reports/index.html", {})


@router.get("/best", response_class=HTMLResponse)
@inject
async def get_best_recordings(
    request: Request,
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of the best recorded audio files based on confidence."""
    try:
        best_recordings = reporting_manager.get_best_detections(limit=20)
    except Exception:
        # If database is not accessible, show empty state
        best_recordings = []
    return templates.TemplateResponse(
        request, "reports/best_recordings.html", {"best_recordings": best_recordings}
    )


@router.get("/detections", response_class=HTMLResponse)
@inject
async def get_detections(
    request: Request,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Retrieve and display all detections."""
    try:
        # Get all detections from the data manager
        all_detections = data_manager.get_all_detections()
        # Convert to dictionary format similar to other reports
        detections_data = [
            {
                "date": d.timestamp.strftime("%Y-%m-%d") if d.timestamp else "",
                "time": d.timestamp.strftime("%H:%M:%S") if d.timestamp else "",
                "scientific_name": d.scientific_name or "",
                "common_name": d.common_name or "",
                "confidence": d.confidence or 0,
                "latitude": d.latitude or "",
                "longitude": d.longitude or "",
            }
            for d in all_detections
        ]
    except Exception:
        # If database is not accessible, show empty state
        detections_data = []
    return templates.TemplateResponse(
        request, "reports/all_detections.html", {"all_detections": detections_data}
    )


@router.get("/today", response_class=HTMLResponse)
@inject
async def get_todays_detections(
    request: Request,
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Retrieve a list of today's detections."""
    try:
        todays_detections = reporting_manager.get_todays_detections()
    except Exception:
        # If database is not accessible, show empty state
        todays_detections = []
    return templates.TemplateResponse(
        request,
        "reports/todays_detections.html",
        {"todays_detections": todays_detections},
    )


@router.get("/weekly", response_class=HTMLResponse)
@inject
async def get_weekly_report(
    request: Request,
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Retrieve and display weekly report data."""
    try:
        weekly_data = reporting_manager.get_weekly_report_data()
    except Exception:
        # If database is not accessible, show empty state
        weekly_data = {
            "start_date": "",
            "end_date": "",
            "week_number": 0,
            "total_detections_current": 0,
            "unique_species_current": 0,
            "total_detections_prior": 0,
            "unique_species_prior": 0,
            "percentage_diff_total": 0,
            "percentage_diff_unique_species": 0,
            "top_10_species": [],
            "new_species": [],
        }
    return templates.TemplateResponse(
        request, "reports/weekly_report.html", {"weekly_data": weekly_data}
    )


@router.get("/charts", response_class=HTMLResponse)
@inject
async def get_charts(
    request: Request,
    reporting_manager: ReportingManager = Depends(  # noqa: B008
        Provide[Container.reporting_manager]
    ),
    plotting_manager: PlottingManager = Depends(  # noqa: B008
        Provide[Container.plotting_manager]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
) -> HTMLResponse:
    """Generate and display various charts related to bird detections."""
    try:
        df = reporting_manager.get_data()

        # Default values for plot generation
        start_date = (
            pd.to_datetime(str(df.index.min())).date()
            if not df.empty
            else pd.Timestamp.now().date()
        )
        end_date = (
            pd.to_datetime(str(df.index.max())).date()
            if not df.empty
            else pd.Timestamp.now().date()
        )
        top_n_count = 10

        species = "All"
        num_days_to_display = getattr(config, "num_days_to_display", 7)  # Default to 7 days
        selected_pal = "Viridis"  # Arbitrary for now

        # Generate multi-day plot
        multi_day_fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
            df, "1h", str(start_date), str(end_date), top_n_count, species
        )
        multi_day_plot_json = pio.to_json(multi_day_fig)

        # Generate daily plot
        # Handle empty DataFrame case for species selection
        most_common_species = (
            df["common_name"].mode()[0]
            if not df.empty and len(df["common_name"].mode()) > 0
            else "All"
        )
        daily_fig = plotting_manager.generate_daily_detections_plot(
            df,
            "15min",
            str(start_date),
            str(most_common_species),
            num_days_to_display,
            selected_pal,
        )
        daily_plot_json = pio.to_json(daily_fig)

        plot_data = {"multi_day_plot": multi_day_plot_json, "daily_plot": daily_plot_json}

        return templates.TemplateResponse(request, "reports/charts.html", {"plot_data": plot_data})
    except Exception:
        # If database is not accessible, show empty charts
        empty_plot_data = {"multi_day_plot": "{}", "daily_plot": "{}"}
        return templates.TemplateResponse(
            request, "reports/charts.html", {"plot_data": empty_plot_data}
        )
