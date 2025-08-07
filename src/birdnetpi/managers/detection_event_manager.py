import logging
from datetime import datetime

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.utils.signals import detection_signal

logger = logging.getLogger(__name__)


class DetectionEventManager:
    """Manages detection events, saving them to the database and triggering notifications."""

    def __init__(
        self, detection_manager: DetectionManager, notification_service: NotificationService
    ) -> None:
        self.detection_manager = detection_manager
        self.notification_service = notification_service
        detection_signal.connect(self.handle_detection_event)  # Register signal handler
        logger.info("DetectionEventManager initialized and listening for signals.")

    async def handle_detection_event(self, sender: object, detection_data: dict) -> None:
        """Handle a detection event received via the Blinker signal."""
        logger.info(f"Processing detection event for {detection_data['species']}")

        # 1. Save detection to database
        # The audio file is already saved to disk by AudioAnalysisService
        # We need to create an AudioFile record and a Detection record

        # Create DetectionEvent from dict data
        detection_event = DetectionEvent(
            species_tensor=detection_data.get("species", ""),
            scientific_name=detection_data.get("species", "").split("_")[0]
            if "_" in detection_data.get("species", "")
            else detection_data.get("species", ""),
            common_name=detection_data.get("species", "").split("_")[1]
            if "_" in detection_data.get("species", "")
            else detection_data.get("species", ""),
            confidence=detection_data["confidence"],
            timestamp=datetime.fromisoformat(detection_data["timestamp"])
            if isinstance(detection_data["timestamp"], str)
            else detection_data["timestamp"],
            audio_file_path=detection_data["audio_file_path"],
            duration=detection_data.get("duration", 0.0),
            size_bytes=detection_data.get("size_bytes", 0),
            spectrogram_path=detection_data.get("spectrogram_path"),
            latitude=detection_data.get("latitude", 0.0),
            longitude=detection_data.get("longitude", 0.0),
            species_confidence_threshold=detection_data.get("species_confidence_threshold", 0.0),
            week=detection_data.get("week", 0),
            sensitivity_setting=detection_data.get("sensitivity_setting", 0.0),
            overlap=detection_data.get("overlap", 0.0),
        )

        logger.info(f"Saving detection to DB: {detection_data['species']}")
        self.detection_manager.create_detection(detection_event)

        # 2. Send WebSocket notification
        # TODO: Implement send_websocket_notification method in NotificationService
        # await self.notification_service.send_websocket_notification(
        #     {
        #         "type": "detection",
        #         "species": detection_data["species"],
        #         "confidence": detection_data["confidence"],
        #         "timestamp": detection_data["timestamp"],
        #     }
        # )

        # 3. Send Apprise notification
        # TODO: Implement send_apprise_notification method in NotificationService
        # await self.notification_service.send_apprise_notification(
        #     title=f"New Bird Detection: {detection_data['species']}",
        #     body=f"Confidence: {detection_data['confidence']:.2f} at {detection_data['timestamp']}",  # noqa: E501
        # )
