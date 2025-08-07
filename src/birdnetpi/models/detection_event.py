from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DetectionEvent(BaseModel):
    """Represents a detection event with associated metadata."""

    # Detection ID (UUID for distributed system compatibility)
    id: UUID | None = None

    # Species identification (parsed from tensor output)
    species_tensor: str  # Raw tensor output: "Scientific_name_Common Name"
    scientific_name: str  # Parsed: "Genus species" (IOC primary key)
    common_name_tensor: str  # Parsed: tensor common name
    common_name_ioc: str | None = None  # IOC canonical English name (resolved via IOC service)

    # Detection metadata
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
    species_confidence_threshold: float | None = None
    week: int | None = None
    sensitivity_setting: float | None = None
    overlap: float | None = None
    is_extracted: bool = False
