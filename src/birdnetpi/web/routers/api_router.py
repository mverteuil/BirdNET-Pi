import logging

from fastapi import APIRouter, Request, status

from birdnetpi.models.api_models import DetectionEventRequest
from birdnetpi.models.detection_event import DetectionEvent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/detections", status_code=status.HTTP_201_CREATED)
async def create_detection(
    detection_request: DetectionEventRequest,
    request: Request,
) -> dict:
    """Receive a new detection event and dispatch it."""
    logger.info(
        f"Received detection: {detection_request.species} "
        f"with confidence {detection_request.confidence}"
    )

    # Convert Pydantic model to dataclass
    detection_event = DetectionEvent(
        species=detection_request.species,
        confidence=detection_request.confidence,
        timestamp=detection_request.timestamp,
        audio_file_path=detection_request.audio_file_path,
        duration=detection_request.duration,
        size_bytes=detection_request.size_bytes,
        recording_start_time=detection_request.recording_start_time,
        spectrogram_path=detection_request.spectrogram_path,
        latitude=detection_request.latitude,
        longitude=detection_request.longitude,
        cutoff=detection_request.cutoff,
        week=detection_request.week,
        sensitivity=detection_request.sensitivity,
        overlap=detection_request.overlap,
        is_extracted=detection_request.is_extracted,
    )

    # Delegate to DetectionManager to create detection and audio file records
    saved_detection = request.app.state.detections.create_detection(detection_event)

    return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}
