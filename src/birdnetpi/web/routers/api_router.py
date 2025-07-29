import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from birdnetpi.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter()


class DetectionEvent(BaseModel):
    """Represents a detection event received from the audio analysis service."""

    species: str
    confidence: float
    timestamp: datetime

    spectrogram_path: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    cutoff: float | None = None
    week: int | None = None
    sensitivity: float | None = None
    overlap: float | None = None
    is_extracted: bool = False
    audio_file_path: str
    duration: float
    size_bytes: int
    recording_start_time: datetime


@router.post("/detections", status_code=status.HTTP_201_CREATED)
async def create_detection(
    detection: DetectionEvent,
    request: Request,
    db: Session = Depends(DatabaseService.get_db),  # noqa: B008
) -> dict:
    """Receive a new detection event and dispatch it."""
    logger.info(f"Received detection: {detection.species} with confidence {detection.confidence}")

    # Delegate to DetectionManager to create detection and audio file records
    saved_detection = request.app.state.detections.create_detection(detection, db)

    return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}
