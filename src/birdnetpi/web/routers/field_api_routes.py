"""Field mode API routes for mobile and field deployments."""

import logging
from datetime import UTC, datetime

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from birdnetpi.managers.data_manager import DataManager
from birdnetpi.managers.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/gps/status")
@inject
async def get_gps_status(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),  # noqa: B008
) -> JSONResponse:
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


@router.get("/gps/location")
@inject
async def get_current_location(
    gps_service: GPSService = Depends(Provide[Container.gps_service]),  # noqa: B008
) -> JSONResponse:
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


@router.get("/gps/history")
@inject
async def get_location_history(
    hours: int = Query(default=24, ge=1, le=168),  # 1 hour to 1 week
    gps_service: GPSService = Depends(Provide[Container.gps_service]),  # noqa: B008
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


@router.get("/hardware/status")
@inject
async def get_hardware_status(
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
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


@router.get("/hardware/component/{component_name}")
@inject
async def get_component_status(
    component_name: str,
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
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
            return JSONResponse(
                {"error": f"Component '{component_name}' not found"}, status_code=404
            )
    except Exception as e:
        logger.error("Error getting component status: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/summary")
@inject
async def get_field_summary(
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    gps_service: GPSService = Depends(Provide[Container.gps_service]),  # noqa: B008
    hardware_monitor: HardwareMonitorManager = Depends(  # noqa: B008
        Provide[Container.hardware_monitor_manager]
    ),
) -> JSONResponse:
    """Get comprehensive field mode summary."""
    try:
        # Get today's detection count
        today = datetime.now(UTC).date()
        counts_by_date = data_manager.count_by_date()
        today_count = counts_by_date.get(today, 0)

        # Get recent detections
        recent_detections = data_manager.get_recent_detections(5)

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
                "timestamp": datetime.now(UTC).isoformat(),
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


@router.post("/alert")
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
