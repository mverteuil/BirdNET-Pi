import logging
from datetime import date, datetime

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()


class LocationUpdate(BaseModel):
    """Location update request model."""

    latitude: float
    longitude: float


@router.post("/", status_code=status.HTTP_201_CREATED)
@inject
async def create_detection(
    detection_event: DetectionEvent,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
) -> dict:
    """Receive a new detection event and dispatch it."""
    logger.info(
        f"Received detection: {detection_event.species_tensor or 'Unknown'} "
        f"with confidence {detection_event.confidence}"
    )

    # Delegate to DetectionManager to create detection and audio file records
    saved_detection = detection_manager.create_detection(detection_event)

    return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}


@router.get("/recent")
@inject
async def get_recent_detections(
    limit: int = 10,
    offset: int = 0,  # Added for compatibility with old endpoint
    language_code: str = "en",
    include_ioc: bool = True,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
) -> JSONResponse:
    """Get recent bird detections with optional IOC taxonomic data."""
    try:
        if include_ioc and detection_manager.detection_query_service:
            # Use IOC-enhanced data
            detections_dict = detection_manager.get_most_recent_detections_with_ioc(
                limit, language_code
            )
            detection_list = [
                {
                    "id": detection_data.get("id"),
                    "scientific_name": detection_data.get("scientific_name", ""),
                    "common_name": detection_data.get("common_name", ""),
                    "confidence": detection_data.get("confidence", 0),
                    "timestamp": detection_data.get("date", "")
                    + "T"
                    + detection_data.get("time", ""),
                    "latitude": detection_data.get("latitude"),
                    "longitude": detection_data.get("longitude"),
                    "ioc_english_name": detection_data.get("ioc_english_name"),
                    "translated_name": detection_data.get("translated_name"),
                    "family": detection_data.get("family"),
                    "genus": detection_data.get("genus"),
                    "order_name": detection_data.get("order_name"),
                }
                for detection_data in detections_dict
            ]
        else:
            # Use regular detection data (fallback)
            detections = detection_manager.get_recent_detections(limit)
            detection_list = [
                {
                    "id": detection.id,
                    "scientific_name": detection.scientific_name,
                    "common_name": detection.common_name,
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
@inject
async def get_detection_count(
    target_date: date | None = None,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
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
@inject
async def update_detection_location(
    detection_id: int,
    location: LocationUpdate,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
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
@inject
async def get_detection(
    detection_id: int,
    language_code: str = "en",
    include_ioc: bool = True,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
) -> JSONResponse:
    """Get a specific detection by ID with optional IOC taxonomic data."""
    try:
        # Try to get IOC-enhanced data first
        if include_ioc and detection_manager.detection_query_service:
            try:
                # Convert int detection_id to UUID format - assuming detection_id is actually a UUID string
                from uuid import UUID

                detection_uuid = (
                    UUID(str(detection_id)) if isinstance(detection_id, str) else detection_id
                )
                detection_with_ioc = (
                    detection_manager.detection_query_service.get_detection_with_ioc_data(
                        detection_uuid, language_code
                    )
                )
                if detection_with_ioc:
                    detection_data = {
                        "id": detection_with_ioc.id,
                        "scientific_name": detection_with_ioc.scientific_name,
                        "common_name": detection_with_ioc.get_best_common_name(
                            prefer_translation=True
                        ),
                        "confidence": detection_with_ioc.confidence,
                        "timestamp": detection_with_ioc.timestamp.isoformat(),
                        "latitude": detection_with_ioc.detection.latitude,
                        "longitude": detection_with_ioc.detection.longitude,
                        "species_confidence_threshold": detection_with_ioc.detection.species_confidence_threshold,
                        "week": detection_with_ioc.detection.week,
                        "sensitivity_setting": detection_with_ioc.detection.sensitivity_setting,
                        "overlap": detection_with_ioc.detection.overlap,
                        "ioc_english_name": detection_with_ioc.ioc_english_name,
                        "translated_name": detection_with_ioc.translated_name,
                        "family": detection_with_ioc.family,
                        "genus": detection_with_ioc.genus,
                        "order_name": detection_with_ioc.order_name,
                    }
                    return JSONResponse(detection_data)
            except Exception as ioc_error:
                logger.warning(
                    "Failed to get IOC data for detection %s: %s", detection_id, ioc_error
                )

        # Fallback to regular detection
        detection = detection_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        detection_data = {
            "id": detection.id,
            "scientific_name": detection.scientific_name,
            "common_name": detection.common_name,
            "confidence": detection.confidence,
            "timestamp": detection.timestamp.isoformat(),
            "latitude": detection.latitude,
            "longitude": detection.longitude,
            "species_confidence_threshold": detection.species_confidence_threshold,
            "week": detection.week,
            "sensitivity_setting": detection.sensitivity_setting,
            "overlap": detection.overlap,
        }
        return JSONResponse(detection_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting detection: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection") from e


@router.get("/{detection_id}/spectrogram")
@inject
async def get_detection_spectrogram(
    detection_id: int,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
    plotting_manager: PlottingManager = Depends(Provide[Container.plotting_manager]),  # noqa: B008
) -> StreamingResponse:
    """Generate and return a spectrogram for a specific detection's audio file."""
    try:
        # Get the detection to find the associated audio file path
        detection = detection_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Get the audio file path from the detection
        if not detection.audio_file_path:
            raise HTTPException(
                status_code=404, detail="No audio file associated with this detection"
            )

        spectrogram_buffer = plotting_manager.generate_spectrogram(detection.audio_file_path)
        return StreamingResponse(content=iter([spectrogram_buffer.read()]), media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating spectrogram for detection %s: %s", detection_id, e)
        raise HTTPException(status_code=500, detail=f"Error generating spectrogram: {e}") from e


@router.get("/species/summary")
@inject
async def get_species_summary(
    language_code: str = "en",
    since: datetime | None = None,
    family_filter: str | None = None,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
) -> JSONResponse:
    """Get detection count summary by species with IOC taxonomic data."""
    try:
        if not detection_manager.detection_query_service:
            raise HTTPException(status_code=503, detail="IOC database service not available")

        species_summary = detection_manager.get_species_summary(
            language_code=language_code, since=since, family_filter=family_filter
        )
        return JSONResponse({"species": species_summary, "count": len(species_summary)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting species summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species summary") from e


@router.get("/families/summary")
@inject
async def get_family_summary(
    language_code: str = "en",
    since: datetime | None = None,
    detection_manager: DetectionManager = Depends(  # noqa: B008
        Provide[Container.detection_manager]
    ),
) -> JSONResponse:
    """Get detection count summary by taxonomic family with IOC data."""
    try:
        if not detection_manager.detection_query_service:
            raise HTTPException(status_code=503, detail="IOC database service not available")

        family_summary = detection_manager.get_family_summary(
            language_code=language_code, since=since
        )
        return JSONResponse({"families": family_summary, "count": len(family_summary)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting family summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving family summary") from e
