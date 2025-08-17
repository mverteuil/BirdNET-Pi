"""Detections domain for bird detection storage, querying, and management."""

from birdnetpi.audio.models import AudioFile
from birdnetpi.detections.bird_detection_service import BirdDetectionService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.database_models import GUID, Detection, PathType
from birdnetpi.detections.detection_query_service import (
    DetectionQueryService,
    DetectionWithLocalization,
)
from birdnetpi.detections.dummy_data_generator import generate_dummy_detections
from birdnetpi.detections.models import DetectionEvent, LocationUpdate
from birdnetpi.models.base import Base

__all__ = [
    "GUID",
    "AudioFile",
    "Base",
    "BirdDetectionService",
    "DataManager",
    "Detection",
    "DetectionEvent",
    "DetectionQueryService",
    "DetectionWithLocalization",
    "LocationUpdate",
    "PathType",
    "generate_dummy_detections",
]
