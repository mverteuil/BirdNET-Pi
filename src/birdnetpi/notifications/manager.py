import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from birdnetpi.config import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.apprise import AppriseService
from birdnetpi.notifications.mqtt import MQTTService
from birdnetpi.notifications.rules import NotificationRuleProcessor
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.notifications.webhooks import WebhookService

logger = logging.getLogger(__name__)


class NotificationManager:
    """Orchestrates sending notifications for detection events across multiple channels."""

    def __init__(
        self,
        active_websockets: set[WebSocket],
        config: BirdNETConfig,
        core_database: CoreDatabaseService,
        species_db_service: SpeciesDatabaseService,
        detection_query_service: DetectionQueryService,
        mqtt_service: MQTTService | None = None,
        webhook_service: WebhookService | None = None,
        apprise_service: AppriseService | None = None,
    ) -> None:
        self.active_websockets = active_websockets
        self.config = config
        self.core_database = core_database
        self.species_db_service = species_db_service
        self.detection_query_service = detection_query_service
        self.mqtt_service = mqtt_service
        self.webhook_service = webhook_service
        self.apprise_service = apprise_service

    def register_listeners(self) -> None:
        """Register Blinker signal listeners."""
        detection_signal.connect(self._handle_detection_event)
        logger.info("NotificationManager listeners registered.")

    def add_websocket(self, websocket: WebSocket) -> None:
        """Add a WebSocket to the active connections set."""
        self.active_websockets.add(websocket)
        logger.info(f"WebSocket added to active connections. Total: {len(self.active_websockets)}")

    def remove_websocket(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active connections set."""
        self.active_websockets.discard(websocket)
        logger.info(
            f"WebSocket removed from active connections. Total: {len(self.active_websockets)}"
        )

    def _handle_detection_event(self, sender: object, detection: Detection) -> None:
        """Handle a new detection event by sending notifications."""
        logger.info(f"NotificationManager received detection: {detection.get_display_name()}")

        # Send WebSocket notifications to connected clients
        if self.active_websockets:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._send_websocket_notifications(detection))
                # Store task reference to avoid potential garbage collection issues
                self._websocket_tasks: set = getattr(self, "_websocket_tasks", set())
                self._websocket_tasks.add(task)
                task.add_done_callback(self._websocket_tasks.discard)
            except RuntimeError:
                logger.debug("No event loop running, skipping WebSocket notifications")

        # Process notification rules for Apprise notifications
        if self.config.notification_rules and self.apprise_service:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._process_notification_rules(detection))
                # Store task reference to avoid potential garbage collection issues
                self._rule_tasks: set = getattr(self, "_rule_tasks", set())
                self._rule_tasks.add(task)
                task.add_done_callback(self._rule_tasks.discard)
            except RuntimeError:
                logger.debug("No event loop running, skipping notification rule processing")

        # Send IoT notifications asynchronously (only if there's a running event loop)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._send_iot_notifications(detection))
            # Store task reference to avoid potential garbage collection issues
            self._background_tasks: set = getattr(self, "_background_tasks", set())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            # No event loop running, skip IoT notifications
            logger.debug("No event loop running, skipping IoT notifications")

    async def _send_websocket_notifications(self, detection: Detection) -> None:
        """Send detection notifications to all connected WebSocket clients."""
        if not self.active_websockets:
            return

        # Create notification payload
        notification_data = {
            "type": "detection",
            "detection": {
                "species": detection.common_name,
                "common_name": detection.common_name,
                "scientific_name": detection.scientific_name,
                "confidence": detection.confidence,
                "datetime": detection.timestamp.isoformat() if detection.timestamp else None,
            },
        }

        notification_json = json.dumps(notification_data)

        # Send to all connected WebSocket clients
        disconnected_websockets = set()
        for ws in self.active_websockets.copy():  # Copy to avoid modification during iteration
            try:
                await ws.send_text(notification_json)
                logger.debug(
                    f"Sent detection notification to WebSocket: {detection.get_display_name()}"
                )
            except Exception as e:
                logger.warning(f"Failed to send WebSocket notification: {e}")
                disconnected_websockets.add(ws)

        # Remove disconnected WebSocket clients
        for ws in disconnected_websockets:
            self.active_websockets.discard(ws)
            logger.info("Removed disconnected WebSocket from active connections")

    async def _send_iot_notifications(self, detection: Detection) -> None:
        """Send MQTT and webhook notifications for a detection event."""
        try:
            # Send MQTT notification
            if self.mqtt_service:
                await self.mqtt_service.publish_detection(detection)
                logger.debug(f"MQTT detection published: {detection.get_display_name()}")

            # Send webhook notification
            if self.webhook_service:
                await self.webhook_service.send_detection_webhook(detection)
                logger.debug(f"Webhook detection sent: {detection.get_display_name()}")

        except Exception as e:
            logger.error(
                f"Error sending IoT notifications for detection {detection.get_display_name()}: {e}"
            )

    async def _process_notification_rules(self, detection: Detection) -> None:
        """Process notification rules and send Apprise/webhook notifications.

        Args:
            detection: Detection to process against rules
        """
        try:
            # Create a database session for rule processing
            async with self.core_database.get_async_db() as session:
                # Attach species databases to session for taxonomy lookups
                await self.species_db_service.attach_all_to_session(session)

                try:
                    # Create rule processor with this session
                    rule_processor = NotificationRuleProcessor(
                        config=self.config,
                        db_session=session,
                        species_db_service=self.species_db_service,
                        detection_query_service=self.detection_query_service,
                    )

                    # Find all matching rules
                    matching_rules = await rule_processor.find_matching_rules(detection)

                    if not matching_rules:
                        logger.debug(
                            "No matching notification rules for detection: %s",
                            detection.get_display_name(),
                        )
                        return

                    # Process each matching rule
                    for rule in matching_rules:
                        await self._send_rule_notification(rule, detection, rule_processor)

                finally:
                    # Always detach databases
                    await self.species_db_service.detach_all_from_session(session)

        except Exception as e:
            logger.error(
                "Error processing notification rules for detection %s: %s",
                detection.get_display_name(),
                e,
            )

    async def _send_rule_notification(
        self,
        rule: dict[str, Any],  # type: ignore[type-arg]
        detection: Detection,
        rule_processor: NotificationRuleProcessor,
    ) -> None:
        """Send notification for a specific rule.

        Args:
            rule: Notification rule configuration
            detection: Detection to send notification for
            rule_processor: Rule processor instance with session context
        """
        rule_name = rule.get("name", "Unnamed")
        service = rule.get("service", "apprise")
        target = rule.get("target", "")

        # Render templates
        title_template = rule.get("title_template", "")
        body_template = rule.get("body_template", "")

        title = rule_processor.render_template(
            title_template,
            detection,
            default_template=self.config.notification_title_default,
        )
        body = rule_processor.render_template(
            body_template,
            detection,
            default_template=self.config.notification_body_default,
        )

        logger.info(
            "Sending notification for rule '%s' to %s target '%s': %s",
            rule_name,
            service,
            target,
            detection.get_display_name(),
        )

        try:
            if service == "apprise" and self.apprise_service:
                await self.apprise_service.send_detection_notification(
                    detection=detection,
                    title=title,
                    body=body,
                    target_name=target if target else None,
                )
            elif service == "webhook" and self.webhook_service:
                # For webhook service, we send to specific target URL
                webhook_url = self.config.webhook_targets.get(target)
                if webhook_url:
                    # TODO: Implement sending to specific webhook target
                    logger.debug("Webhook notification to %s would be sent here", webhook_url)
                else:
                    logger.warning("Webhook target '%s' not found in config", target)
            elif service == "mqtt" and self.mqtt_service:
                # For MQTT, use the target as topic suffix
                # TODO: Implement MQTT notification with custom topic
                logger.debug("MQTT notification to topic '%s' would be sent here", target)
            else:
                logger.warning(
                    "Service '%s' not available or not supported for rule '%s'", service, rule_name
                )

        except Exception as e:
            logger.error("Error sending notification for rule '%s': %s", rule_name, e)

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
