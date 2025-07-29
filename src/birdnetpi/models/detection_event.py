from dataclasses import dataclass
from datetime import datetime


@dataclass
class DetectionEvent:
    """Represents a detection event with associated metadata."""

    species: str
    confidence: float
    timestamp: datetime
    audio_file_path: str
