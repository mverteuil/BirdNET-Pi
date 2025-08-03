import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.detection_event import DetectionEvent

logger = logging.getLogger(__name__)

router = APIRouter()


class LocationUpdate(BaseModel):
    """Location update request model."""

    latitude: float
    longitude: float


def get_detection_manager(request: Request) -> DetectionManager:
    """Return the DetectionManager instance from the app state."""
    return request.app.state.detections


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_detection(
    detection_event: DetectionEvent,
    request: Request,
) -> dict:
    """Receive a new detection event and dispatch it."""
    logger.info(
        f"Received detection: {detection_event.species_tensor or 'Unknown'} "
        f"with confidence {detection_event.confidence}"
    )

    # Delegate to DetectionManager to create detection and audio file records
    saved_detection = request.app.state.detections.create_detection(detection_event)

    return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}


@router.get("/recent")
async def get_recent_detections(
    limit: int = 10,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> JSONResponse:
    """Get recent bird detections."""
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
        raise HTTPException(status_code=500, detail="Error retrieving recent detections") from e


@router.get("/count")
async def get_detection_count(
    target_date: date | None = None,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> JSONResponse:
    """Get detection count for a specific date (defaults to today)."""
    try:
        if target_date is None:
            target_date = datetime.now().date()

        count = detection_manager.get_detections_count_by_date(target_date)
        return JSONResponse({"date": target_date.isoformat(), "count": count})
    except Exception as e:
        logger.error("Error getting detection count: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection count") from e


@router.post("/{detection_id}/location")
async def update_detection_location(
    detection_id: int,
    location: LocationUpdate,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> JSONResponse:
    """Update detection location with GPS coordinates."""
    try:
        # Get the detection
        detection = detection_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Update the location
        success = detection_manager.update_detection_location(
            detection_id, location.latitude, location.longitude
        )

        if success:
            return JSONResponse(
                {
                    "message": "Location updated successfully",
                    "detection_id": detection_id,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                }
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to update detection location")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating detection location: %s", e)
        raise HTTPException(status_code=500, detail="Error updating detection location") from e


@router.get("/{detection_id}")
async def get_detection(
    detection_id: int,
    detection_manager: DetectionManager = Depends(get_detection_manager),  # noqa: B008
) -> JSONResponse:
    """Get a specific detection by ID."""
    try:
        detection = detection_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        detection_data = {
            "id": detection.id,
            "species": detection.species,
            "confidence": detection.confidence,
            "timestamp": detection.timestamp.isoformat(),
            "latitude": detection.latitude,
            "longitude": detection.longitude,
            "cutoff": detection.cutoff,
            "week": detection.week,
            "sensitivity": detection.sensitivity,
            "overlap": detection.overlap,
        }
        return JSONResponse(detection_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting detection: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection") from e
