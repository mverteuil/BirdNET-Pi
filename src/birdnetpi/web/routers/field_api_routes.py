"""Field mode API routes for mobile-optimized field operations."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/gps/status")
@inject
async def get_gps_status(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),
) -> dict:
    """Get GPS service status."""
    return {
        "enabled": gps_service.enable_gps,
        "active": gps_service.enable_gps and hasattr(gps_service, "_gps_task"),
        "update_interval": gps_service.update_interval,
    }


@router.get("/gps/location")
@inject
async def get_gps_location(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),
) -> dict:
    """Get current GPS location."""
    if not gps_service.enable_gps:
        raise HTTPException(status_code=404, detail="GPS service is not enabled")

    location = gps_service.get_current_location()
    return {"location": location}


@router.get("/gps/history")
@inject
async def get_gps_history(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),
    hours: int = 24,
) -> dict:
    """Get GPS location history."""
    if not gps_service.enable_gps:
        raise HTTPException(status_code=404, detail="GPS service is not enabled")

    history = gps_service.get_location_history(hours=hours)
    return {"history": history, "hours": hours}


@router.get("/summary")
@inject
async def get_field_summary(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),
    hardware_monitor: HardwareMonitorService = Depends(Provide[Container.hardware_monitor_service]),
    detection_manager: DetectionManager = Depends(Provide[Container.detection_manager]),
) -> dict:
    """Get field mode summary with GPS, hardware, and detection data."""
    summary = {
        "gps": {
            "enabled": gps_service.enable_gps,
            "location": gps_service.get_current_location() if gps_service.enable_gps else None,
        },
        "hardware": hardware_monitor.get_all_status(),
        "detections": {
            "today_count": 0,  # TODO: Implement get_todays_detections method
            "recent": detection_manager.get_recent_detections(limit=5),
        },
    }
    return summary


@router.post("/alert")
@inject
async def create_field_alert(
    alert_data: dict,
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),
    webhook_service: WebhookService = Depends(Provide[Container.webhook_service]),
) -> JSONResponse:
    """Create and send field mode alert."""
    # Send alert via MQTT if enabled
    if mqtt_service.enable_mqtt:
        # TODO: Implement publish_message method
        pass

    # Send alert via webhooks if enabled
    if webhook_service.enable_webhooks:
        # TODO: Implement send_webhook method
        pass

    return JSONResponse({"status": "alert_sent", "data": alert_data})