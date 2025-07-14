from dataclasses import dataclass
from datetime import datetime


@dataclass
class AudioMetadata:
    """Represents metadata for an audio recording."""

    file_path: str
    duration: float
    size_bytes: int
    recording_start_time: datetime
    # Add other relevant audio metadata fields as needed
