"""Database models - re-exported from appropriate domains for backward compatibility."""

from birdnetpi.audio.models import AudioFile
from birdnetpi.detections.database_models import GUID, Detection, PathType
from birdnetpi.models.base import Base

__all__ = ["GUID", "AudioFile", "Base", "Detection", "PathType"]
