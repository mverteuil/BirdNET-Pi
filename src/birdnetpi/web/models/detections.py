"""Detection-related API contract models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DetectionEvent(BaseModel):
    """Represents a detection event with associated metadata."""

    # Detection ID (UUID for distributed system compatibility)
    id: UUID | None = None

    # Species identification (parsed from tensor output)
    species_tensor: str  # Raw tensor output: "Scientific name_Common Name"
    scientific_name: str  # Parsed: "Genus species" (IOC primary key)
    common_name: str  # Standardized common name from tensor

    # Detection metadata
    confidence: float
    timestamp: datetime

    # Audio data
    audio_data: str  # Base64-encoded audio bytes
    sample_rate: int
    channels: int

    # Optional fields
    spectrogram_path: str | None = None
    latitude: float
    longitude: float
    species_confidence_threshold: float
    week: int
    sensitivity_setting: float
    overlap: float


class LocationUpdate(BaseModel):
    """Request model for updating location settings."""

    latitude: float
    longitude: float
