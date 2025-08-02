"""Field mode API routes for mobile and field deployments."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_detection_manager(request: Request) -> DetectionManager:
    """Get DetectionManager from app state."""
    return request.app.state.detections


def get_gps_service(request: Request) -> GPSService | None:
    """Get GPSService from app state."""
    return getattr(request.app.state, "gps_service", None)


def get_hardware_monitor(request: Request) -> HardwareMonitorService | None:
    """Get HardwareMonitorService from app state."""
    return getattr(request.app.state, "hardware_monitor", None)


@router.get("/field", response_class=HTMLResponse)
async def get_field_mode(request: Request) -> HTMLResponse:
    """Render the field mode interface."""
    return request.app.state.templates.TemplateResponse("field_mode.html", {"request": request})


@router.get("/api/gps/status")
async def get_gps_status(gps_service: GPSService | None = Depends(get_gps_service)) -> JSONResponse:
    """Get current GPS status and location information."""
    if not gps_service:
        return JSONResponse(
            {
                "enabled": False,
                "available": False,
                "message": "GPS service not initialized",
            }
        )

    try:
        status = gps_service.get_gps_status()
        return JSONResponse(status)
    except Exception as e:
        logger.error("Error getting GPS status: %s", e)
        return JSONResponse(
            {
                "enabled": gps_service.enable_gps,
                "available": False,
                "error": str(e),
            },
            status_code=500,
        )


@router.get("/api/gps/location")
async def get_current_location(gps_service: GPSService | None = Depends(get_gps_service)) -> JSONResponse:
    """Get current GPS coordinates."""
    if not gps_service:
        return JSONResponse({"error": "GPS service not available"}, status_code=404)

    try:
        location = gps_service.get_current_location()
        if location:
            return JSONResponse(
                {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "altitude": location.altitude,
                    "accuracy": location.accuracy,
                    "timestamp": location.timestamp.isoformat(),
                    "satellite_count": location.satellite_count,
                }
            )
        else:
            return JSONResponse({"error": "No GPS fix available"}, status_code=404)
    except Exception as e:
        logger.error("Error getting GPS location: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/gps/history")
async def get_location_history(
    hours: int = Query(default=24, ge=1, le=168),  # 1 hour to 1 week
    gps_service: GPSService | None = Depends(get_gps_service),
) -> JSONResponse:
    """Get GPS location history."""
    if not gps_service:
        return JSONResponse({"error": "GPS service not available"}, status_code=404)

    try:
        history = gps_service.get_location_history(hours)
        locations = [
            {
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "altitude": loc.altitude,
                "accuracy": loc.accuracy,
                "timestamp": loc.timestamp.isoformat(),
                "satellite_count": loc.satellite_count,
            }
            for loc in history
        ]
        return JSONResponse({"locations": locations, "count": len(locations)})
    except Exception as e:
        logger.error("Error getting GPS history: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/hardware/status")
async def get_hardware_status(
    hardware_monitor: HardwareMonitorService | None = Depends(get_hardware_monitor),
) -> JSONResponse:
    """Get comprehensive hardware status."""
    if not hardware_monitor:
        return JSONResponse(
            {
                "available": False,
                "message": "Hardware monitoring not enabled",
                "components": {},
            }
        )

    try:
        status = hardware_monitor.get_health_summary()
        return JSONResponse(status)
    except Exception as e:
        logger.error("Error getting hardware status: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/hardware/component/{component_name}")
async def get_component_status(
    component_name: str,
    hardware_monitor: HardwareMonitorService | None = Depends(get_hardware_monitor),
) -> JSONResponse:
    """Get status for a specific hardware component."""
    if not hardware_monitor:
        return JSONResponse({"error": "Hardware monitoring not available"}, status_code=404)

    try:
        component_status = hardware_monitor.get_component_status(component_name)
        if component_status:
            return JSONResponse(
                {
                    "name": component_status.name,
                    "status": component_status.status.value,
                    "message": component_status.message,
                    "last_check": component_status.last_check.isoformat(),
                    "details": component_status.details,
                }
            )
        else:
            return JSONResponse({"error": f"Component '{component_name}' not found"}, status_code=404)
    except Exception as e:
        logger.error("Error getting component status: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/detections/recent")
async def get_recent_detections(
    limit: int = Query(default=10, ge=1, le=100),
    detection_manager: DetectionManager = Depends(get_detection_manager),
) -> JSONResponse:
    """Get recent bird detections for field mode display."""
    try:
        detections = detection_manager.get_recent_detections(limit)
        detection_list = [
            {
                "id": detection.id,
                "species": detection.species,
                "confidence": detection.confidence,
                "timestamp": detection.timestamp.isoformat(),
                "latitude": detection.latitude,
                "longitude": detection.longitude,
            }
            for detection in detections
        ]
        return JSONResponse({"detections": detection_list, "count": len(detection_list)})
    except Exception as e:
        logger.error("Error getting recent detections: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/detections/count")
async def get_detection_count(
    date: str | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    detection_manager: DetectionManager = Depends(get_detection_manager),
) -> JSONResponse:
    """Get detection count for a specific date (defaults to today)."""
    try:
        if date:
            try:
                target_date = datetime.fromisoformat(date).date()
            except ValueError:
                return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status_code=400)
        else:
            target_date = datetime.now(timezone.utc).date()

        count = detection_manager.get_detections_count_by_date(target_date)
        return JSONResponse({"date": target_date.isoformat(), "count": count})
    except Exception as e:
        logger.error("Error getting detection count: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/detections/{detection_id}/location")
async def update_detection_location(
    detection_id: int,
    request: Request,
    detection_manager: DetectionManager = Depends(get_detection_manager),
    gps_service: GPSService | None = Depends(get_gps_service),
) -> JSONResponse:
    """Update detection location with current GPS coordinates."""
    try:
        # Get current location
        if not gps_service:
            return JSONResponse({"error": "GPS service not available"}, status_code=404)

        location = gps_service.get_current_location()
        if not location:
            return JSONResponse({"error": "No GPS fix available"}, status_code=404)

        # Get the detection
        detection = detection_manager.get_detection_by_id(detection_id)
        if not detection:
            return JSONResponse({"error": "Detection not found"}, status_code=404)

        # Update location
        detection_manager.update_detection_location(detection_id, location.latitude, location.longitude)

        return JSONResponse(
            {
                "detection_id": detection_id,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.error("Error updating detection location: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/field/summary")
async def get_field_summary(
    detection_manager: DetectionManager = Depends(get_detection_manager),
    gps_service: GPSService | None = Depends(get_gps_service),
    hardware_monitor: HardwareMonitorService | None = Depends(get_hardware_monitor),
) -> JSONResponse:
    """Get comprehensive field mode summary."""
    try:
        # Get today's detection count
        today = datetime.now(timezone.utc).date()
        today_count = detection_manager.get_detections_count_by_date(today)

        # Get recent detections
        recent_detections = detection_manager.get_recent_detections(5)

        # Get GPS status
        gps_status = {"enabled": False}
        if gps_service:
            gps_status = gps_service.get_gps_status()

        # Get hardware status
        hardware_status = {"overall_status": "unknown"}
        if hardware_monitor:
            hardware_status = hardware_monitor.get_health_summary()

        return JSONResponse(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "detections": {
                    "today_count": today_count,
                    "recent": [
                        {
                            "species": d.species,
                            "confidence": d.confidence,
                            "timestamp": d.timestamp.isoformat(),
                        }
                        for d in recent_detections
                    ],
                },
                "gps": gps_status,
                "hardware": hardware_status,
            }
        )
    except Exception as e:
        logger.error("Error getting field summary: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/field/alert")
async def trigger_field_alert(request: Request) -> JSONResponse:
    """Trigger a field mode alert (for testing)."""
    try:
        body = await request.json()
        message = body.get("message", "Test alert")
        level = body.get("level", "info")  # info, warning, critical

        logger.info("Field mode alert triggered: %s (level: %s)", message, level)

        # TODO: Implement alert notification system
        # This could send notifications via Apprise, WebSocket, etc.

        return JSONResponse({"message": "Alert triggered", "level": level, "text": message})
    except Exception as e:
        logger.error("Error triggering field alert: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)