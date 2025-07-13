from utils.signals import detection_event


class DetectionEventPublisher:
    def publish_detection(self, detection_data: dict):
        """Publishes a detection event."""
        detection_event.send(self, data=detection_data)
