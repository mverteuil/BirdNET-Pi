"""Admin routes for system management, settings, logs, and testing."""

import datetime
import logging

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.services.log_service import LogService
from birdnetpi.utils.config_file_parser import ConfigFileParser

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin")
async def read_admin() -> dict[str, str]:
    """Return a simple message indicating the admin router is working."""
    return {"message": "Admin router is working!"}


# Settings Management
@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request) -> Response:
    """Render the settings page with the current configuration."""
    config_parser = ConfigFileParser(
        request.app.state.file_manager.file_path_resolver.get_birdnetpi_config_path()
    )
    app_config: BirdNETConfig = config_parser.load_config()
    return request.app.state.templates.TemplateResponse(
        "settings.html", {"request": request, "config": app_config}
    )


@router.post("/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    site_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    model: str = Form(...),
    species_confidence_threshold: float = Form(...),
    birdweather_id: str = Form(""),
    apprise_input: str = Form(""),
    apprise_notification_title: str = Form(""),
    apprise_notification_body: str = Form(""),
    apprise_notify_each_detection: bool = Form(False),
    apprise_notify_new_species: bool = Form(False),
    apprise_notify_new_species_each_day: bool = Form(False),
    apprise_weekly_report: bool = Form(False),
    minimum_time_limit: int = Form(0),
    flickr_api_key: str = Form(""),
    flickr_filter_email: str = Form(""),
    database_lang: str = Form("en"),
    timezone: str = Form("UTC"),
    caddy_pwd: str = Form(""),
    silence_update_indicator: bool = Form(False),
    birdnetpi_url: str = Form(""),
    apprise_only_notify_species_names: str = Form(""),
    apprise_only_notify_species_names_2: str = Form(""),
) -> RedirectResponse:
    """Process the submitted settings form and save the updated configuration."""
    config_parser = ConfigFileParser(
        request.app.state.file_manager.file_path_resolver.get_birdnetpi_config_path()
    )
    updated_config = BirdNETConfig(
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        model=model,
        species_confidence_threshold=species_confidence_threshold,
        birdweather_id=birdweather_id,
        apprise_input=apprise_input,
        apprise_notification_title=apprise_notification_title,
        apprise_notification_body=apprise_notification_body,
        apprise_notify_each_detection=apprise_notify_each_detection,
        apprise_notify_new_species=apprise_notify_new_species,
        apprise_notify_new_species_each_day=apprise_notify_new_species_each_day,
        apprise_weekly_report=apprise_weekly_report,
        minimum_time_limit=minimum_time_limit,
        flickr_api_key=flickr_api_key,
        flickr_filter_email=flickr_filter_email,
        database_lang=database_lang,
        timezone=timezone,
        caddy_pwd=caddy_pwd,
        silence_update_indicator=silence_update_indicator,
        birdnetpi_url=birdnetpi_url,
        apprise_only_notify_species_names=apprise_only_notify_species_names,
        apprise_only_notify_species_names_2=apprise_only_notify_species_names_2,
    )
    config_parser.save_config(updated_config)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


# Log Management
@router.get("/log", response_class=PlainTextResponse)
async def get_log_content() -> PlainTextResponse:
    """Retrieve the BirdNET-Pi service logs."""
    try:
        log_service = LogService()
        logs = log_service.get_logs()
        return logs
    except Exception as e:
        logger.error("Error retrieving logs: %s", e)
        return PlainTextResponse(f"Error retrieving logs: {e!s}", status_code=500)


# Notification Testing
@router.get("/test_detection_form", response_class=HTMLResponse)
async def test_detection_form(request: Request) -> HTMLResponse:
    """Render the form for testing detections."""
    return request.app.state.templates.TemplateResponse(request, "test_detection_modal.html", {})


@router.get("/test_detection")
async def test_detection(
    request: Request,
    species: str = "Test Bird",
    confidence: float = 0.99,
    timestamp: str | None = None,
    audio_file_path: str = "test_audio/test_bird.wav",
    duration: float = 3.0,
    size_bytes: int = 1024,
    recording_start_time: str | None = None,
    latitude: float = 0.0,
    longitude: float = 0.0,
    cutoff: float = 0.0,
    week: int = 0,
    sensitivity: float = 0.0,
    overlap: float = 0.0,
) -> dict[str, str]:
    """Publishes a test detection event for demonstration purposes."""
    detection_event_data = DetectionEvent(
        species=species,
        confidence=confidence,
        timestamp=datetime.datetime.fromisoformat(timestamp)
        if timestamp
        else datetime.datetime.now(),
        audio_file_path=audio_file_path,
        duration=duration,
        size_bytes=size_bytes,
        recording_start_time=datetime.datetime.fromisoformat(recording_start_time)
        if recording_start_time
        else datetime.datetime.now(),
        latitude=latitude,
        longitude=longitude,
        cutoff=cutoff,
        week=week,
        sensitivity=sensitivity,
        overlap=overlap,
    )
    request.app.state.detections.create_detection(detection_event_data)
    return {"message": "Test detection published", "data": detection_event_data.model_dump_json()}
