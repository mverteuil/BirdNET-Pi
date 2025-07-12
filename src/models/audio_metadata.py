from dataclasses import dataclass
from datetime import datetime

@dataclass
class AudioMetadata:
    file_path: str
    duration: float
    size_bytes: int
    recording_start_time: datetime
    # Add other relevant audio metadata fields as needed
