import pandas as pd
import plotly.io as pio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.managers.update_manager import UpdateManager

router = APIRouter()

templates = Jinja2Templates(directory="src/web/templates")


def get_detection_manager(request: Request) -> DetectionManager:
    """Return the DetectionManager instance from the app state."""
    return request.app.state.detections


@router.get("/views", response_class=HTMLResponse)
async def read_views(
    request: Request,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> HTMLResponse:
    """Render the main views page, displaying repository update status."""
    update_manager = UpdateManager()
    commits_behind_count = update_manager.get_commits_behind()
    return templates.TemplateResponse(
        "views.html", {"request": request, "commits_behind": commits_behind_count}
    )


@router.get("/views/weekly-report", response_class=HTMLResponse)
async def get_weekly_report(
    request: Request,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> HTMLResponse:
    """Generate and display a weekly report of bird detections."""
    reporting_manager = ReportingManager(detection_manager)
    report_data = reporting_manager.get_weekly_report_data()
    return templates.TemplateResponse(
        "weekly_report.html", {"request": request, "report": report_data}
    )


@router.get("/views/charts", response_class=HTMLResponse)
async def get_charts(
    request: Request,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> HTMLResponse:
    """Generate and display various charts related to bird detections."""
    reporting_manager = ReportingManager(detection_manager)
    plotting_manager = PlottingManager()
    df = reporting_manager.get_data()

    # Default values for plot generation
    start_date = pd.to_datetime(df.index.min()).date()
    end_date = pd.to_datetime(df.index.max()).date()
    top_n = 10

    specie = "All"
    num_days_to_display = request.app.state.config.data.num_days_to_display
    selected_pal = "Viridis"  # Arbitrary for now

    # Generate multi-day plot
    multi_day_fig = plotting_manager.generate_multi_day_species_and_hourly_plot(
        df, "Hourly", start_date, end_date, top_n, specie
    )
    multi_day_plot_json = pio.to_json(multi_day_fig)

    # Generate daily plot
    daily_fig = plotting_manager.generate_daily_detections_plot(
        df,
        "15 minutes",
        start_date,
        df["Com_Name"].mode()[0],
        num_days_to_display,
        selected_pal,
    )
    daily_plot_json = pio.to_json(daily_fig)

    plot_data = {"multi_day_plot": multi_day_plot_json, "daily_plot": daily_plot_json}

    return templates.TemplateResponse("charts.html", {"request": request, "plot_data": plot_data})


@router.get("/livestream", response_class=HTMLResponse)
async def get_livestream(request: Request) -> HTMLResponse:
    """Render the audio livestream page."""
    websocket_url = f"ws://{request.url.hostname}:{request.url.port}/ws/audio"
    return templates.TemplateResponse(
        "livestream.html", {"request": request, "websocket_url": websocket_url}
    )


@router.get("/spectrogram", response_class=HTMLResponse)
async def get_spectrogram(request: Request) -> HTMLResponse:
    """Render the real-time spectrogram visualization page."""
    audio_websocket_url = f"ws://{request.url.hostname}:{request.url.port}/ws/audio"
    spectrogram_websocket_url = f"ws://{request.url.hostname}:{request.url.port}/ws/spectrogram"
    return templates.TemplateResponse(
        "spectrogram.html",
        {
            "request": request,
            "audio_websocket_url": audio_websocket_url,
            "spectrogram_websocket_url": spectrogram_websocket_url,
        },
    )
