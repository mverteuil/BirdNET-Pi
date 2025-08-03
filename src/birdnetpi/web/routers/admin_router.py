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
    # Basic Settings
    site_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    model: str = Form(...),
    metadata_model: str = Form(...),
    species_confidence_threshold: float = Form(...),
    confidence: float = Form(...),
    sensitivity: float = Form(...),
    week: int = Form(...),
    audio_format: str = Form(...),
    extraction_length: float = Form(...),
    audio_device_index: int = Form(...),
    sample_rate: int = Form(...),
    audio_channels: int = Form(...),
    # External Services
    birdweather_id: str = Form(""),
    # Notifications
    apprise_input: str = Form(""),
    apprise_notification_title: str = Form(""),
    apprise_notification_body: str = Form(""),
    apprise_notify_each_detection: bool = Form(False),
    apprise_notify_new_species: bool = Form(False),
    apprise_notify_new_species_each_day: bool = Form(False),
    apprise_weekly_report: bool = Form(False),
    minimum_time_limit: int = Form(0),
    # Flickr
    flickr_api_key: str = Form(""),
    flickr_filter_email: str = Form(""),
    # Localization
    database_lang: str = Form("en"),
    language_code: str = Form("en"),
    species_display_mode: str = Form("full"),
    timezone: str = Form("UTC"),
    # Web Settings
    caddy_pwd: str = Form(""),
    silence_update_indicator: bool = Form(False),
    birdnetpi_url: str = Form(""),
    # Species Filtering
    apprise_only_notify_species_names: str = Form(""),
    apprise_only_notify_species_names_2: str = Form(""),
    # Field Mode and GPS
    enable_gps: bool = Form(False),
    gps_update_interval: float = Form(5.0),
    hardware_check_interval: float = Form(10.0),
    enable_audio_device_check: bool = Form(True),
    enable_system_resource_check: bool = Form(True),
    enable_gps_check: bool = Form(False),
    # Analysis
    privacy_threshold: float = Form(10.0),
    # MQTT Integration
    enable_mqtt: bool = Form(False),
    mqtt_broker_host: str = Form("localhost"),
    mqtt_broker_port: int = Form(1883),
    mqtt_username: str = Form(""),
    mqtt_password: str = Form(""),
    mqtt_topic_prefix: str = Form("birdnet"),
    mqtt_client_id: str = Form("birdnet-pi"),
    # Webhook Integration
    enable_webhooks: bool = Form(False),
    webhook_urls: str = Form(""),  # Will be parsed as comma-separated list
    webhook_events: str = Form("detection,health,gps,system"),
) -> RedirectResponse:
    """Process the submitted settings form and save the updated configuration."""
    config_parser = ConfigFileParser(
        request.app.state.file_manager.file_path_resolver.get_birdnetpi_config_path()
    )
    # Parse webhook URLs from comma-separated string to list
    webhook_urls_list = (
        [url.strip() for url in webhook_urls.split(",") if url.strip()] if webhook_urls else []
    )

    updated_config = BirdNETConfig(
        # Basic Settings
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        model=model,
        metadata_model=metadata_model,
        species_confidence_threshold=species_confidence_threshold,
        confidence=confidence,
        sensitivity=sensitivity,
        week=week,
        audio_format=audio_format,
        extraction_length=extraction_length,
        audio_device_index=audio_device_index,
        sample_rate=sample_rate,
        audio_channels=audio_channels,
        # External Services
        birdweather_id=birdweather_id,
        # Notifications
        apprise_input=apprise_input,
        apprise_notification_title=apprise_notification_title,
        apprise_notification_body=apprise_notification_body,
        apprise_notify_each_detection=apprise_notify_each_detection,
        apprise_notify_new_species=apprise_notify_new_species,
        apprise_notify_new_species_each_day=apprise_notify_new_species_each_day,
        apprise_weekly_report=apprise_weekly_report,
        minimum_time_limit=minimum_time_limit,
        # Flickr
        flickr_api_key=flickr_api_key,
        flickr_filter_email=flickr_filter_email,
        # Localization
        database_lang=database_lang,
        language_code=language_code,
        species_display_mode=species_display_mode,
        timezone=timezone,
        # Web Settings
        caddy_pwd=caddy_pwd,
        silence_update_indicator=silence_update_indicator,
        birdnetpi_url=birdnetpi_url,
        # Species Filtering
        apprise_only_notify_species_names=apprise_only_notify_species_names,
        apprise_only_notify_species_names_2=apprise_only_notify_species_names_2,
        # Field Mode and GPS
        enable_gps=enable_gps,
        gps_update_interval=gps_update_interval,
        hardware_check_interval=hardware_check_interval,
        enable_audio_device_check=enable_audio_device_check,
        enable_system_resource_check=enable_system_resource_check,
        enable_gps_check=enable_gps_check,
        # Analysis
        privacy_threshold=privacy_threshold,
        # MQTT Integration
        enable_mqtt=enable_mqtt,
        mqtt_broker_host=mqtt_broker_host,
        mqtt_broker_port=mqtt_broker_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_topic_prefix=mqtt_topic_prefix,
        mqtt_client_id=mqtt_client_id,
        # Webhook Integration
        enable_webhooks=enable_webhooks,
        webhook_urls=webhook_urls_list,
        webhook_events=webhook_events,
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
