"""Web API contract models using Pydantic for validation."""

from birdnetpi.detections.models import DetectionEvent, LocationUpdate
from birdnetpi.web.models.admin import YAMLConfigRequest

__all__ = [
    "DetectionEvent",
    "LocationUpdate",
    "YAMLConfigRequest",
]
