from birdnetpi.models.database_models import Detection
from birdnetpi.utils.signals import detection_signal


class DetectionEventPublisher:
    """Publishes detection events to connected listeners."""

    def publish_detection(self, detection_data: dict) -> None:
        """Publish a detection event."""
        detection_obj = Detection(**detection_data)
        detection_signal.send(self, detection=detection_obj)
