"""System API routes for hardware monitoring."""

import time

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.system.status import SystemInspector
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/hardware/status")
@inject
async def get_hardware_status(
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> dict:
    """Get comprehensive hardware and system status.

    This endpoint provides all system metrics needed for monitoring,
    including health summary, detailed system info, and detection count.
    """
    # Get base health summary
    health_summary = SystemInspector.get_health_summary()

    # Get detailed system info
    system_info = SystemInspector.get_system_info()

    # Get total detections
    total_detections = await detection_query_service.count_detections()

    # Calculate uptime in days from boot time
    boot_time = system_info.get("boot_time", time.time())
    uptime_seconds = time.time() - boot_time
    uptime_days = int(uptime_seconds // 86400)

    # Combine all data for comprehensive status
    return {
        **health_summary,  # Include base health summary
        "system_info": {
            "device_name": system_info.get("device_name", "Unknown"),
            "platform": system_info.get("platform", "Unknown"),
            "cpu_count": system_info.get("cpu_count", 0),
            "uptime_days": uptime_days,
        },
        "resources": {
            "cpu": {
                "percent": system_info.get("cpu_percent", 0),
                "temperature": system_info.get("cpu_temperature"),
            },
            "memory": system_info.get("memory", {}),
            "disk": system_info.get("disk", {}),
        },
        "total_detections": total_detections,
    }
