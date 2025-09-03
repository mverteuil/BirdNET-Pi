"""Admin routes for system management, settings, logs, and testing."""

import datetime
import json
import logging
from datetime import UTC

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from birdnetpi.audio.devices import AudioDeviceService
from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.detections.manager import DataManager
from birdnetpi.system.log_service import LogService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.detections import DetectionEvent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def read_admin() -> dict[str, str]:
    """Return a simple message indicating the admin router is working."""
    return {"message": "Admin router is working!"}


# Settings Management
@router.get("/settings", response_class=HTMLResponse)
@inject
async def get_settings(
    request: Request,
    path_resolver: PathResolver = Depends(  # noqa: B008
        Provide[Container.path_resolver]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> Response:
    """Render the settings page with the current configuration."""
    config_manager = ConfigManager(path_resolver)
    app_config: BirdNETConfig = config_manager.load()

    # Get available audio devices
    audio_device_service = AudioDeviceService()
    audio_devices = audio_device_service.discover_input_devices()

    # Get available model files
    models_path = path_resolver.get_models_dir()
    model_files = []
    metadata_model_files = []

    if models_path.exists():
        # Find all .tflite model files
        for model_file in models_path.glob("*.tflite"):
            # Use stem (filename without extension) for config storage
            model_name = model_file.stem
            # Separate metadata models from main models
            if "MData" in model_name or "metadata" in model_name.lower():
                metadata_model_files.append(model_name)
            else:
                model_files.append(model_name)

    # Sort the lists for consistent display
    model_files.sort()
    metadata_model_files.sort()

    # Normalize config model names by removing .tflite extension if present
    # This ensures the comparison in the template works correctly
    normalized_config = app_config.model_copy()
    if normalized_config.model and normalized_config.model.endswith(".tflite"):
        normalized_config.model = normalized_config.model[:-7]  # Remove .tflite
    if normalized_config.metadata_model and normalized_config.metadata_model.endswith(".tflite"):
        normalized_config.metadata_model = normalized_config.metadata_model[:-7]  # Remove .tflite

    return templates.TemplateResponse(
        request,
        "admin/settings.html.j2",
        {
            "config": normalized_config,
            "audio_devices": audio_devices,
            "model_files": model_files,
            "metadata_model_files": metadata_model_files,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
@inject
async def post_settings(
    # Basic Settings (required)
    site_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    model: str = Form(...),
    metadata_model: str = Form(...),
    species_confidence_threshold: float = Form(...),
    sensitivity: float = Form(...),
    audio_device_index: int = Form(...),
    sample_rate: int = Form(...),
    audio_channels: int = Form(...),
    analysis_overlap: float = Form(...),
    # External Services (optional - preserves existing if not provided)
    birdweather_id: str | None = Form(None),
    # New notification fields (JSON) - optional
    apprise_targets_json: str | None = Form(None),
    webhook_targets_json: str | None = Form(None),
    notification_rules_json: str | None = Form(None),
    # Flickr (optional)
    flickr_api_key: str | None = Form(None),
    flickr_filter_email: str | None = Form(None),
    # Localization (optional)
    language: str | None = Form(None),
    species_display_mode: str | None = Form(None),
    timezone: str | None = Form(None),
    # Field Mode and GPS (optional)
    enable_gps: bool | None = Form(None),
    gps_update_interval: float | None = Form(None),
    hardware_check_interval: float | None = Form(None),
    enable_audio_device_check: bool | None = Form(None),
    enable_system_resource_check: bool | None = Form(None),
    enable_gps_check: bool | None = Form(None),
    # Analysis (optional)
    privacy_threshold: float | None = Form(None),
    # MQTT Integration (optional)
    enable_mqtt: bool | None = Form(None),
    mqtt_broker_host: str | None = Form(None),
    mqtt_broker_port: int | None = Form(None),
    mqtt_username: str | None = Form(None),
    mqtt_password: str | None = Form(None),
    mqtt_topic_prefix: str | None = Form(None),
    mqtt_client_id: str | None = Form(None),
    # Webhook Integration (optional)
    enable_webhooks: bool | None = Form(None),
    webhook_urls: str | None = Form(None),  # Will be parsed as comma-separated list
    webhook_events: str | None = Form(None),
    path_resolver: PathResolver = Depends(  # noqa: B008
        Provide[Container.path_resolver]
    ),
) -> RedirectResponse:
    """Process the submitted settings form and save the updated configuration.

    Only updates fields that were actually provided in the form.
    Preserves existing values for fields not included in the basic settings form.
    """
    config_manager = ConfigManager(path_resolver)

    # Load current config to preserve fields not in the form
    current_config = config_manager.load()

    # Parse JSON notification data if provided
    if apprise_targets_json is not None:
        try:
            apprise_targets = json.loads(apprise_targets_json) if apprise_targets_json else {}
        except json.JSONDecodeError as e:
            logger.error("Error parsing apprise targets JSON: %s", e)
            apprise_targets = current_config.apprise_targets
    else:
        apprise_targets = current_config.apprise_targets

    if webhook_targets_json is not None:
        try:
            webhook_targets = json.loads(webhook_targets_json) if webhook_targets_json else {}
        except json.JSONDecodeError as e:
            logger.error("Error parsing webhook targets JSON: %s", e)
            webhook_targets = current_config.webhook_targets
    else:
        webhook_targets = current_config.webhook_targets

    if notification_rules_json is not None:
        try:
            notification_rules = (
                json.loads(notification_rules_json) if notification_rules_json else []
            )
        except json.JSONDecodeError as e:
            logger.error("Error parsing notification rules JSON: %s", e)
            notification_rules = current_config.notification_rules
    else:
        notification_rules = current_config.notification_rules

    # Parse webhook URLs from comma-separated string to list if provided
    if webhook_urls is not None:
        webhook_urls_list = (
            [url.strip() for url in webhook_urls.split(",") if url.strip()] if webhook_urls else []
        )
    else:
        webhook_urls_list = current_config.webhook_urls

    updated_config = BirdNETConfig(
        # System fields (always preserved)
        config_version=current_config.config_version,
        logging=current_config.logging,
        # Basic Settings (always from form)
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        model=model,
        metadata_model=metadata_model,
        species_confidence_threshold=species_confidence_threshold,
        sensitivity_setting=sensitivity,
        audio_device_index=audio_device_index,
        sample_rate=sample_rate,
        audio_channels=audio_channels,
        analysis_overlap=analysis_overlap,
        # External Services (preserve if not provided)
        birdweather_id=birdweather_id
        if birdweather_id is not None
        else current_config.birdweather_id,
        # New Notification System (preserve if not provided)
        apprise_targets=apprise_targets,
        webhook_targets=webhook_targets,
        notification_rules=notification_rules,
        notification_title_default=current_config.notification_title_default,
        notification_body_default=current_config.notification_body_default,
        notify_quiet_hours_start=current_config.notify_quiet_hours_start,
        notify_quiet_hours_end=current_config.notify_quiet_hours_end,
        # Flickr (preserve if not provided)
        flickr_api_key=flickr_api_key
        if flickr_api_key is not None
        else current_config.flickr_api_key,
        flickr_filter_email=flickr_filter_email
        if flickr_filter_email is not None
        else current_config.flickr_filter_email,
        # Localization (preserve if not provided)
        language=language if language is not None else current_config.language,
        species_display_mode=species_display_mode
        if species_display_mode is not None
        else current_config.species_display_mode,
        timezone=timezone if timezone is not None else current_config.timezone,
        # Field Mode and GPS (preserve if not provided)
        enable_gps=enable_gps if enable_gps is not None else current_config.enable_gps,
        gps_update_interval=gps_update_interval
        if gps_update_interval is not None
        else current_config.gps_update_interval,
        hardware_check_interval=hardware_check_interval
        if hardware_check_interval is not None
        else current_config.hardware_check_interval,
        enable_audio_device_check=enable_audio_device_check
        if enable_audio_device_check is not None
        else current_config.enable_audio_device_check,
        enable_system_resource_check=enable_system_resource_check
        if enable_system_resource_check is not None
        else current_config.enable_system_resource_check,
        enable_gps_check=enable_gps_check
        if enable_gps_check is not None
        else current_config.enable_gps_check,
        # Analysis (preserve if not provided)
        privacy_threshold=privacy_threshold
        if privacy_threshold is not None
        else current_config.privacy_threshold,
        # MQTT Integration (preserve if not provided)
        enable_mqtt=enable_mqtt if enable_mqtt is not None else current_config.enable_mqtt,
        mqtt_broker_host=mqtt_broker_host
        if mqtt_broker_host is not None
        else current_config.mqtt_broker_host,
        mqtt_broker_port=mqtt_broker_port
        if mqtt_broker_port is not None
        else current_config.mqtt_broker_port,
        mqtt_username=mqtt_username if mqtt_username is not None else current_config.mqtt_username,
        mqtt_password=mqtt_password if mqtt_password is not None else current_config.mqtt_password,
        mqtt_topic_prefix=mqtt_topic_prefix
        if mqtt_topic_prefix is not None
        else current_config.mqtt_topic_prefix,
        mqtt_client_id=mqtt_client_id
        if mqtt_client_id is not None
        else current_config.mqtt_client_id,
        # Webhook Integration (preserve if not provided)
        enable_webhooks=enable_webhooks
        if enable_webhooks is not None
        else current_config.enable_webhooks,
        webhook_urls=webhook_urls_list,
        webhook_events=webhook_events
        if webhook_events is not None
        else current_config.webhook_events,
        # Git settings (always preserved from current config)
        git_remote=current_config.git_remote,
        git_branch=current_config.git_branch,
    )
    config_manager.save(updated_config)
    logger.info("Settings saved successfully")

    return RedirectResponse(url="/admin/settings", status_code=HTTP_303_SEE_OTHER)


# Log Management
@router.get("/log", response_class=PlainTextResponse)
async def get_log_content() -> PlainTextResponse:
    """Retrieve the BirdNET-Pi service logs."""
    try:
        log_service = LogService()
        logs = log_service.get_logs()
        return PlainTextResponse(logs)
    except Exception as e:
        logger.error("Error retrieving logs: %s", e)
        return PlainTextResponse(f"Error retrieving logs: {e!s}", status_code=500)


# Notification Testing
@router.get("/test_detection_form", response_class=HTMLResponse)
@inject
async def test_detection_form(
    request: Request,
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> HTMLResponse:
    """Render the form for testing detections."""
    return templates.TemplateResponse(request, "admin/test_detection_modal.html", {})


@router.get("/test_detection")
@inject
async def test_detection(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    species: str = "Test Bird",
    confidence: float = 0.99,
    timestamp: str | None = None,
    latitude: float = 0.0,
    longitude: float = 0.0,
    species_confidence_threshold: float = 0.0,
    week: int = 0,
    sensitivity_setting: float = 0.0,
    overlap: float = 0.0,
) -> dict[str, str]:
    """Publishes a test detection event for demonstration purposes."""
    # Convert species to required format
    # (assuming format: "Common Name" -> "Genus species_Common Name")
    if "_" in species:
        # Already in tensor format
        species_tensor = species
        scientific_name, common_name = species.split("_", 1)
    else:
        # Convert single name to tensor format (use generic genus for test)
        species_tensor = f"Testus species_{species}"
        scientific_name = "Testus species"
        common_name = species

    # Create test audio data for the detection
    import base64

    test_audio_bytes = b"test audio data for detection"
    encoded_audio = base64.b64encode(test_audio_bytes).decode("utf-8")

    detection_event_data = DetectionEvent(
        species_tensor=species_tensor,
        scientific_name=scientific_name,
        common_name=common_name,
        confidence=confidence,
        timestamp=datetime.datetime.fromisoformat(timestamp)
        if timestamp
        else datetime.datetime.now(UTC),
        audio_data=encoded_audio,  # Base64-encoded audio
        sample_rate=48000,  # Standard sample rate
        channels=1,  # Mono audio
        latitude=latitude,
        longitude=longitude,
        species_confidence_threshold=species_confidence_threshold,
        week=week,
        sensitivity_setting=sensitivity_setting,
        overlap=overlap,
    )
    await data_manager.create_detection(detection_event_data)
    return {"message": "Test detection published", "data": detection_event_data.model_dump_json()}


# Advanced YAML Editor
@router.get("/advanced-settings", response_class=HTMLResponse)
@inject
async def get_advanced_settings(
    request: Request,
    path_resolver: PathResolver = Depends(  # noqa: B008
        Provide[Container.path_resolver]
    ),
    templates: Jinja2Templates = Depends(Provide[Container.templates]),  # noqa: B008
) -> Response:
    """Render the advanced YAML configuration editor."""
    config_manager = ConfigManager(path_resolver)
    # Load raw YAML content for editor
    config_yaml = config_manager.config_path.read_text()

    return templates.TemplateResponse(
        request, "admin/advanced_settings.html.j2", {"config_yaml": config_yaml}
    )
