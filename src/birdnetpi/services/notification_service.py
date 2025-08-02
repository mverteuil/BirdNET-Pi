import asyncio
import logging

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.utils.signals import detection_signal

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles sending notifications for detection events."""

    def __init__(
        self,
        active_websockets: set,
        config: BirdNETConfig,
        mqtt_service: MQTTService | None = None,
        webhook_service: WebhookService | None = None,
    ) -> None:
        self.active_websockets = active_websockets
        self.config = config
        self.mqtt_service = mqtt_service
        self.webhook_service = webhook_service

    def register_listeners(self) -> None:
        """Register Blinker signal listeners."""
        detection_signal.connect(self._handle_detection_event)
        logger.info("NotificationService listeners registered.")

    def _handle_detection_event(self, sender: object, detection: Detection) -> None:
        """Handle a new detection event by sending notifications."""
        logger.info(f"NotificationService received detection: {detection.species}")

        # Send WebSocket notifications (existing functionality)
        for _ws in self.active_websockets:
            # In a real async app, you'd await ws.send_json or similar
            logger.info(f"Simulating sending detection to websocket: {detection.species}")

        # Send Apprise notifications (existing functionality)
        if self.config.apprise_notify_each_detection:
            logger.info(f"Simulating sending Apprise notification for: {detection.species}")

        # Send IoT notifications asynchronously
        task = asyncio.create_task(self._send_iot_notifications(detection))
        # Store task reference to avoid potential garbage collection issues
        self._background_tasks = getattr(self, '_background_tasks', set())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _send_iot_notifications(self, detection: Detection) -> None:
        """Send MQTT and webhook notifications for a detection event."""
        try:
            # Send MQTT notification
            if self.mqtt_service:
                await self.mqtt_service.publish_detection(detection)
                logger.debug(f"MQTT detection published: {detection.species}")

            # Send webhook notification
            if self.webhook_service:
                await self.webhook_service.send_detection_webhook(detection)
                logger.debug(f"Webhook detection sent: {detection.species}")

        except Exception as e:
            logger.error(f"Error sending IoT notifications for detection {detection.species}: {e}")

    async def send_system_health_notification(self, health_data: dict) -> None:
        """Send system health notifications to IoT services."""
        try:
            # Send MQTT health notification
            if self.mqtt_service:
                await self.mqtt_service.publish_system_health(health_data)
                logger.debug("MQTT system health published")

            # Send webhook health notification
            if self.webhook_service:
                await self.webhook_service.send_health_webhook(health_data)
                logger.debug("Webhook system health sent")

        except Exception as e:
            logger.error(f"Error sending system health IoT notifications: {e}")

    async def send_gps_notification(
        self, latitude: float, longitude: float, accuracy: float | None = None
    ) -> None:
        """Send GPS location notifications to IoT services."""
        try:
            # Send MQTT GPS notification
            if self.mqtt_service:
                await self.mqtt_service.publish_gps_location(latitude, longitude, accuracy)
                logger.debug(f"MQTT GPS location published: {latitude}, {longitude}")

            # Send webhook GPS notification
            if self.webhook_service:
                await self.webhook_service.send_gps_webhook(latitude, longitude, accuracy)
                logger.debug(f"Webhook GPS location sent: {latitude}, {longitude}")

        except Exception as e:
            logger.error(f"Error sending GPS IoT notifications: {e}")

    async def send_system_stats_notification(self, stats_data: dict) -> None:
        """Send system statistics notifications to IoT services."""
        try:
            # Send MQTT system stats notification
            if self.mqtt_service:
                await self.mqtt_service.publish_system_stats(stats_data)
                logger.debug("MQTT system stats published")

            # Send webhook system stats notification
            if self.webhook_service:
                await self.webhook_service.send_system_webhook(stats_data)
                logger.debug("Webhook system stats sent")

        except Exception as e:
            logger.error(f"Error sending system stats IoT notifications: {e}")
