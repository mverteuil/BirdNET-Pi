"""Detections domain for bird detection storage, querying, and management."""

from birdnetpi.detections.bird_detection_service import BirdDetectionService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import (
    DetectionQueryService,
    DetectionWithLocalization,
)
from birdnetpi.detections.dummy_data_generator import generate_dummy_detections
from birdnetpi.detections.models import DetectionEvent, LocationUpdate

__all__ = [
    "BirdDetectionService",
    "DataManager",
    "DetectionEvent",
    "DetectionQueryService",
    "DetectionWithLocalization",
    "LocationUpdate",
    "generate_dummy_detections",
]
