from datetime import datetime

from pydantic import BaseModel


class DetectionEvent(BaseModel):
    """Represents a detection event with associated metadata."""

    species: str
    confidence: float
    timestamp: datetime
    audio_file_path: str
    duration: float
    size_bytes: int
    recording_start_time: datetime

    # Optional fields
    spectrogram_path: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    cutoff: float | None = None
    week: int | None = None
    sensitivity: float | None = None
    overlap: float | None = None
    is_extracted: bool = False
