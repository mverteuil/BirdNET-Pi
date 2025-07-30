import logging

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.utils.signals import detection_signal

logger = logging.getLogger(__name__)


class DetectionEventProcessor:
    """Processes detection events, saving them to the database and triggering notifications."""

    def __init__(
        self, detection_manager: DetectionManager, notification_service: NotificationService
    ) -> None:
        self.detection_manager = detection_manager
        self.notification_service = notification_service
        detection_signal.connect(self.handle_detection_event)  # Register signal handler
        logger.info("DetectionEventProcessor initialized and listening for signals.")

    async def handle_detection_event(self, sender: object, detection_data: dict) -> None:
        """Handle a detection event received via the Blinker signal."""
        logger.info(f"Processing detection event for {detection_data['species']}")

        # 1. Save detection to database
        # The audio file is already saved to disk by AudioAnalysisService
        # We need to create an AudioFile record and a Detection record

        # Create AudioFile record
        # Assuming duration and size_bytes can be derived or passed
        # For now, dummy values or derive from raw_audio_bytes if still available
        logger.info(f"Simulating saving detection to DB: {detection_data['species']}")
        self.detection_manager.create_detection(detection_data)  # Actual call

        # 2. Send WebSocket notification
        await self.notification_service.send_websocket_notification(
            {
                "type": "detection",
                "species": detection_data["species"],
                "confidence": detection_data["confidence"],
                "timestamp": detection_data["timestamp"],
            }
        )

        # 3. Send Apprise notification
        await self.notification_service.send_apprise_notification(
            title=f"New Bird Detection: {detection_data['species']}",
            body=f"Confidence: {detection_data['confidence']:.2f} at {detection_data['timestamp']}",
        )
