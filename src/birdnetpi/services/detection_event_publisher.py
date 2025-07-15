from birdnetpi.utils.signals import detection_event


class DetectionEventPublisher:
    """Publishes detection events to connected listeners."""

    def publish_detection(self, detection_data: dict) -> None:
        """Publish a detection event."""
        detection_event.send(self, data=detection_data)
