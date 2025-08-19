"""Web API contract models using Pydantic for validation."""

from birdnetpi.web.models.admin import YAMLConfigRequest
from birdnetpi.web.models.detections import DetectionEvent, LocationUpdate

__all__ = [
    "DetectionEvent",
    "LocationUpdate",
    "YAMLConfigRequest",
]
