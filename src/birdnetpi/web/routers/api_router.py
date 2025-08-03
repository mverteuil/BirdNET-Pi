"""Centralized API router containing all API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService

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
