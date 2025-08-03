"""Centralized API router containing all API endpoints."""

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.config import BirdNETConfig
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.utils.config_file_parser import ConfigFileParser

router = APIRouter()


# Dependency injection functions
def get_detection_manager(request: Request) -> DetectionManager:
    """Get the detection manager from app state."""
    return request.app.state.detections


def get_gps_service(request: Request) -> GPSService:
    """Get the GPS service from app state."""
    return request.app.state.gps_service


def get_hardware_monitor(request: Request) -> HardwareMonitorService:
    """Get the hardware monitor service from app state."""
    return request.app.state.hardware_monitor


def get_mqtt_service(request: Request) -> MQTTService:
    """Get the MQTT service from app state."""
    return request.app.state.mqtt_service


def get_webhook_service(request: Request) -> WebhookService:
    """Get the webhook service from app state."""
    return request.app.state.webhook_service


# Detection API endpoints
@router.get("/detections")
async def get_detections(
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get recent detections."""
    detections = detection_manager.get_recent_detections(limit=limit, offset=offset)
    return {"detections": detections, "count": len(detections)}


# GPS API endpoints
@router.get("/gps/status")
async def get_gps_status(
    gps_service: GPSService = Depends(get_gps_service),  # noqa: B008
) -> dict:
    """Get GPS service status."""
    return {
        "enabled": gps_service.enabled,
        "active": gps_service.enabled and hasattr(gps_service, "_gps_task"),
        "update_interval": gps_service.update_interval,
    }


@router.get("/gps/location")
async def get_gps_location(
    gps_service: GPSService = Depends(get_gps_service),  # noqa: B008
) -> dict:
    """Get current GPS location."""
    if not gps_service.enabled:
        raise HTTPException(status_code=404, detail="GPS service is not enabled")

    location = gps_service.get_current_location()
    return {"location": location}


@router.get("/gps/history")
async def get_gps_history(
    gps_service: GPSService = Depends(get_gps_service),  # noqa: B008
    hours: int = 24,
) -> dict:
    """Get GPS location history."""
    if not gps_service.enabled:
        raise HTTPException(status_code=404, detail="GPS service is not enabled")

    history = gps_service.get_location_history(hours=hours)
    return {"history": history, "hours": hours}


# Hardware monitoring API endpoints
@router.get("/hardware/status")
async def get_hardware_status(
    hardware_monitor: HardwareMonitorService = Depends(get_hardware_monitor),  # noqa: B008
) -> dict:
    """Get hardware monitoring status."""
    return hardware_monitor.get_system_status()


@router.get("/hardware/component/{component_name}")
async def get_hardware_component(
    component_name: str,
    hardware_monitor: HardwareMonitorService = Depends(get_hardware_monitor),  # noqa: B008
) -> dict:
    """Get specific hardware component status."""
    status = hardware_monitor.get_component_status(component_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")
    return {"component": component_name, "status": status}


# Field mode API endpoints
@router.get("/field/summary")
async def get_field_summary(
    gps_service: GPSService = Depends(get_gps_service),  # noqa: B008
    hardware_monitor: HardwareMonitorService = Depends(get_hardware_monitor),  # noqa: B008
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> dict:
    """Get field mode summary with GPS, hardware, and detection data."""
    summary = {
        "gps": {
            "enabled": gps_service.enabled,
            "location": gps_service.get_current_location() if gps_service.enabled else None,
        },
        "hardware": hardware_monitor.get_system_status(),
        "detections": {
            "today_count": len(detection_manager.get_todays_detections()),
            "recent": detection_manager.get_recent_detections(limit=5),
        },
    }
    return summary


@router.post("/field/alert")
async def create_field_alert(
    alert_data: dict,
    mqtt_service: MQTTService = Depends(get_mqtt_service),  # noqa: B008
    webhook_service: WebhookService = Depends(get_webhook_service),  # noqa: B008
) -> JSONResponse:
    """Create and send field mode alert."""
    # Send alert via MQTT if enabled
    if mqtt_service.enabled:
        await mqtt_service.publish_message("field/alert", alert_data)

    # Send alert via webhooks if enabled
    if webhook_service.enabled:
        await webhook_service.send_webhook("field_alert", alert_data)

    return JSONResponse({"status": "alert_sent", "data": alert_data})


# IoT integration endpoints
@router.get("/iot/mqtt/status")
async def get_mqtt_status(
    mqtt_service: MQTTService = Depends(get_mqtt_service),  # noqa: B008
) -> dict:
    """Get MQTT service status."""
    return {
        "enabled": mqtt_service.enabled,
        "connected": mqtt_service.is_connected() if mqtt_service.enabled else False,
        "broker_host": mqtt_service.broker_host if mqtt_service.enabled else None,
        "broker_port": mqtt_service.broker_port if mqtt_service.enabled else None,
    }


@router.get("/iot/webhooks/status")
async def get_webhook_status(
    webhook_service: WebhookService = Depends(get_webhook_service),  # noqa: B008
) -> dict:
    """Get webhook service status."""
    return {
        "enabled": webhook_service.enabled,
        "configured_urls": len(webhook_service.webhook_urls) if webhook_service.enabled else 0,
    }


@router.post("/iot/test")
async def test_iot_services(
    mqtt_service: MQTTService = Depends(get_mqtt_service),  # noqa: B008
    webhook_service: WebhookService = Depends(get_webhook_service),  # noqa: B008
) -> dict:
    """Test IoT service connectivity."""
    results = {"mqtt": False, "webhooks": False}

    if mqtt_service.enabled:
        results["mqtt"] = mqtt_service.is_connected()

    if webhook_service.enabled:
        # Test webhook connectivity (simplified)
        results["webhooks"] = len(webhook_service.webhook_urls) > 0

    return {"test_results": results}


# Configuration API endpoints for YAML editor
class YAMLConfigRequest(BaseModel):
    """Request model for YAML configuration operations."""

    yaml_content: str


@router.post("/config/validate")
async def validate_yaml_config(
    request: Request,
    config_request: YAMLConfigRequest,
) -> dict:
    """Validate YAML configuration content."""
    try:
        # Parse YAML
        config_data = yaml.safe_load(config_request.yaml_content)

        # Create a temporary ConfigFileParser to validate
        config_parser = ConfigFileParser(
            request.app.state.file_manager.file_path_resolver.get_birdnetpi_config_path()
        )

        # Try to parse into BirdNETConfig model
        # This will validate all fields and types
        BirdNETConfig(
            site_name=config_data.get("site_name", "BirdNET-Pi"),
            latitude=float(config_data.get("latitude", 0.0)),
            longitude=float(config_data.get("longitude", 0.0)),
            model=config_data.get("model", "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite"),
            metadata_model=config_data.get(
                "metadata_model", "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"
            ),
            species_confidence_threshold=float(
                config_data.get("species_confidence_threshold", config_data.get("sf_thresh", 0.03))
            ),
            confidence=float(config_data.get("confidence", 0.7)),
            sensitivity=float(config_data.get("sensitivity", 1.25)),
            week=int(config_data.get("week", 0)),
            audio_format=config_data.get("audio_format", "mp3"),
            extraction_length=float(config_data.get("extraction_length", 6.0)),
            birdweather_id=config_data.get("birdweather_id", ""),
            apprise_input=config_data.get("apprise_input", ""),
            apprise_notification_title=config_data.get("apprise_notification_title", ""),
            apprise_notification_body=config_data.get("apprise_notification_body", ""),
            apprise_notify_each_detection=bool(
                config_data.get("apprise_notify_each_detection", False)
            ),
            apprise_notify_new_species=bool(config_data.get("apprise_notify_new_species", False)),
            apprise_notify_new_species_each_day=bool(
                config_data.get("apprise_notify_new_species_each_day", False)
            ),
            apprise_weekly_report=bool(config_data.get("apprise_weekly_report", False)),
            minimum_time_limit=int(config_data.get("minimum_time_limit", 0)),
            flickr_api_key=config_data.get("flickr_api_key", ""),
            flickr_filter_email=config_data.get("flickr_filter_email", ""),
            database_lang=config_data.get("database_lang", "en"),
            language_code=config_data.get("language_code", "en"),
            species_display_mode=config_data.get("species_display_mode", "full"),
            timezone=config_data.get("timezone", "UTC"),
            caddy_pwd=config_data.get("caddy_pwd", ""),
            silence_update_indicator=bool(config_data.get("silence_update_indicator", False)),
            birdnetpi_url=config_data.get("birdnetpi_url", ""),
            apprise_only_notify_species_names=config_data.get(
                "apprise_only_notify_species_names", ""
            ),
            apprise_only_notify_species_names_2=config_data.get(
                "apprise_only_notify_species_names_2", ""
            ),
            audio_device_index=int(config_data.get("audio_device_index", -1)),
            sample_rate=int(config_data.get("sample_rate", 48000)),
            audio_channels=int(config_data.get("audio_channels", 1)),
            enable_gps=bool(config_data.get("enable_gps", False)),
            gps_update_interval=float(config_data.get("gps_update_interval", 5.0)),
            hardware_check_interval=float(config_data.get("hardware_check_interval", 10.0)),
            enable_audio_device_check=bool(config_data.get("enable_audio_device_check", True)),
            enable_system_resource_check=bool(
                config_data.get("enable_system_resource_check", True)
            ),
            enable_gps_check=bool(config_data.get("enable_gps_check", False)),
            privacy_threshold=float(config_data.get("privacy_threshold", 10.0)),
            enable_mqtt=bool(config_data.get("enable_mqtt", False)),
            mqtt_broker_host=config_data.get("mqtt_broker_host", "localhost"),
            mqtt_broker_port=int(config_data.get("mqtt_broker_port", 1883)),
            mqtt_username=config_data.get("mqtt_username", ""),
            mqtt_password=config_data.get("mqtt_password", ""),
            mqtt_topic_prefix=config_data.get("mqtt_topic_prefix", "birdnet"),
            mqtt_client_id=config_data.get("mqtt_client_id", "birdnet-pi"),
            enable_webhooks=bool(config_data.get("enable_webhooks", False)),
            webhook_urls=config_parser._parse_webhook_urls(config_data.get("webhook_urls", [])),
        )

        return {"valid": True, "message": "Configuration is valid"}

    except yaml.YAMLError as e:
        return {"valid": False, "error": f"YAML syntax error: {e!s}"}
    except ValueError as e:
        return {"valid": False, "error": f"Configuration value error: {e!s}"}
    except Exception as e:
        return {"valid": False, "error": f"Validation error: {e!s}"}


@router.post("/config/save")
async def save_yaml_config(
    request: Request,
    config_request: YAMLConfigRequest,
) -> dict:
    """Save YAML configuration content."""
    try:
        # First validate the YAML
        validation_result = await validate_yaml_config(request, config_request)
        if not validation_result["valid"]:
            return {"success": False, "error": validation_result["error"]}

        # Get config file path
        config_path = request.app.state.file_manager.file_path_resolver.get_birdnetpi_config_path()

        # Write the raw YAML content
        with open(config_path, "w") as f:
            f.write(config_request.yaml_content)

        return {"success": True, "message": "Configuration saved successfully"}

    except Exception as e:
        return {"success": False, "error": f"Failed to save configuration: {e!s}"}
