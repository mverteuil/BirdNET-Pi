import logging

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.utils.signals import detection_signal

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles sending notifications for detection events."""

    def __init__(self, active_websockets: set, config: BirdNETConfig) -> None:
        self.active_websockets = active_websockets
        self.config = config

    def register_listeners(self) -> None:
        """Register Blinker signal listeners."""
        detection_signal.connect(self._handle_detection_event)
        logger.info("NotificationService listeners registered.")

    def _handle_detection_event(self, sender: object, detection: Detection) -> None:
        """Handle a new detection event by sending notifications."""
        logger.info(f"NotificationService received detection: {detection.species}")
        # TODO: Implement WebSocket and Apprise notifications here
        # For now, just log
        for _ws in self.active_websockets:
            # In a real async app, you'd await ws.send_json or similar
            logger.info(f"Simulating sending detection to websocket: {detection.species}")

        if self.config.apprise_notify_each_detection:
            logger.info(f"Simulating sending Apprise notification for: {detection.species}")
