"""MQTT service for IoT integration and real-time event publishing.

This service publishes detection events, system status, and field mode data
to MQTT brokers for integration with home automation systems and IoT platforms.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import paho.mqtt.client as mqtt

from birdnetpi.models.database_models import Detection

logger = logging.getLogger(__name__)


class MQTTService:
    """MQTT service for publishing BirdNET-Pi events and status."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        topic_prefix: str = "birdnet",
        client_id: str = "birdnet-pi",
        enable_mqtt: bool = False,
    ) -> None:
        """Initialize MQTT service.

        Args:
            broker_host: MQTT broker hostname or IP
            broker_port: MQTT broker port
            username: Optional MQTT username
            password: Optional MQTT password
            topic_prefix: Prefix for all MQTT topics
            client_id: MQTT client identifier
            enable_mqtt: Whether MQTT publishing is enabled
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client_id = client_id
        self.enable_mqtt = enable_mqtt

        self.client: mqtt.Client | None = None
        self.is_connected = False
        self.connection_retry_count = 0
        self.max_retries = 5

        # Topic structure
        self.topics = {
            "detections": f"{topic_prefix}/detections",
            "status": f"{topic_prefix}/status",
            "health": f"{topic_prefix}/health",
            "gps": f"{topic_prefix}/gps",
            "system": f"{topic_prefix}/system",
            "config": f"{topic_prefix}/config",
        }

    async def start(self) -> None:
        """Start MQTT service and connect to broker."""
        if not self.enable_mqtt:
            logger.info("MQTT service disabled")
            return

        logger.info("Starting MQTT service...")

        try:
            # Create MQTT client
            self.client = mqtt.Client(client_id=self.client_id)

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish

            # Set authentication if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            # Connect to broker
            await self._connect_with_retry()

        except Exception as e:
            logger.error("Failed to start MQTT service: %s", e)

    async def stop(self) -> None:
        """Stop MQTT service and disconnect from broker."""
        if not self.enable_mqtt or not self.client:
            return

        logger.info("Stopping MQTT service...")

        try:
            if self.is_connected:
                # Publish offline status
                await self._publish_status("offline")
                self.client.disconnect()

            self.is_connected = False
            self.client = None

        except Exception as e:
            logger.error("Error stopping MQTT service: %s", e)

    async def _connect_with_retry(self) -> None:
        """Connect to MQTT broker with retry logic."""
        while self.connection_retry_count < self.max_retries:
            try:
                logger.info(
                    "Connecting to MQTT broker %s:%d (attempt %d/%d)",
                    self.broker_host,
                    self.broker_port,
                    self.connection_retry_count + 1,
                    self.max_retries,
                )

                # Connect asynchronously
                result = self.client.connect(self.broker_host, self.broker_port, 60)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    # Start the network loop in a separate thread
                    self.client.loop_start()
                    # Wait a bit for connection to establish
                    await asyncio.sleep(2)
                    break
                else:
                    raise Exception(f"Connection failed with code: {result}")

            except Exception as e:
                self.connection_retry_count += 1
                logger.warning(
                    "MQTT connection attempt %d failed: %s",
                    self.connection_retry_count,
                    e,
                )

                if self.connection_retry_count < self.max_retries:
                    await asyncio.sleep(5 * self.connection_retry_count)  # Exponential backoff
                else:
                    logger.error("Max MQTT connection retries reached. Giving up.")
                    raise

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: dict, rc: int) -> None:  # noqa: ANN401
        """Handle successful MQTT connection callback."""
        if rc == 0:
            self.is_connected = True
            self.connection_retry_count = 0
            logger.info("Connected to MQTT broker successfully")

            # Store task references to avoid potential garbage collection issues
            self._background_tasks = getattr(self, "_background_tasks", set())

            # Publish online status
            task1 = asyncio.create_task(self._publish_status("online"))
            self._background_tasks.add(task1)
            task1.add_done_callback(self._background_tasks.discard)

            # Publish system information
            task2 = asyncio.create_task(self._publish_system_info())
            self._background_tasks.add(task2)
            task2.add_done_callback(self._background_tasks.discard)
        else:
            logger.error("MQTT connection failed with code: %d", rc)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:  # noqa: ANN401
        """Handle MQTT disconnection callback."""
        self.is_connected = False
        if rc != 0:
            logger.warning("Unexpected MQTT disconnection (code: %d)", rc)
        else:
            logger.info("MQTT disconnected gracefully")

    def _on_publish(self, client: mqtt.Client, userdata: Any, mid: int) -> None:  # noqa: ANN401
        """Handle successful message publishing callback."""
        logger.debug("MQTT message published (mid: %d)", mid)

    async def publish_detection(self, detection: Detection) -> bool:
        """Publish bird detection event to MQTT.

        Args:
            detection: Detection object to publish

        Returns:
            True if published successfully, False otherwise
        """
        if not self._can_publish():
            return False

        try:
            # Prepare detection payload
            payload = {
                "timestamp": detection.timestamp.isoformat(),
                "species": detection.get_display_name(),
                "confidence": detection.confidence,
                "location": {
                    "latitude": detection.latitude,
                    "longitude": detection.longitude,
                }
                if detection.latitude and detection.longitude
                else None,
                "analysis": {
                    "cutoff": detection.cutoff,
                    "week": detection.week,
                    "sensitivity": detection.sensitivity,
                    "overlap": detection.overlap,
                },
                "detection_id": detection.id,
            }

            # Publish to detections topic
            result = self.client.publish(
                self.topics["detections"],
                json.dumps(payload),
                qos=1,
                retain=False,
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(
                    "Published detection: %s (%.2f)",
                    detection.get_display_name(),
                    detection.confidence,
                )
                return True
            else:
                logger.error("Failed to publish detection (code: %d)", result.rc)
                return False

        except Exception as e:
            logger.error("Error publishing detection to MQTT: %s", e)
            return False

    async def publish_gps_location(
        self, latitude: float, longitude: float, accuracy: float | None = None
    ) -> bool:
        """Publish GPS location update to MQTT.

        Args:
            latitude: GPS latitude
            longitude: GPS longitude
            accuracy: Optional GPS accuracy in meters

        Returns:
            True if published successfully, False otherwise
        """
        if not self._can_publish():
            return False

        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
            }

            result = self.client.publish(
                self.topics["gps"],
                json.dumps(payload),
                qos=1,
                retain=True,  # Retain GPS location
            )

            return result.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error("Error publishing GPS location to MQTT: %s", e)
            return False

    async def publish_system_health(self, health_data: dict[str, Any]) -> bool:
        """Publish system health status to MQTT.

        Args:
            health_data: System health information

        Returns:
            True if published successfully, False otherwise
        """
        if not self._can_publish():
            return False

        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                **health_data,
            }

            result = self.client.publish(
                self.topics["health"],
                json.dumps(payload),
                qos=1,
                retain=True,  # Retain health status
            )

            return result.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error("Error publishing system health to MQTT: %s", e)
            return False

    async def publish_system_stats(self, stats: dict[str, Any]) -> bool:
        """Publish system statistics to MQTT.

        Args:
            stats: System statistics (CPU, memory, disk usage, etc.)

        Returns:
            True if published successfully, False otherwise
        """
        if not self._can_publish():
            return False

        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                **stats,
            }

            result = self.client.publish(
                self.topics["system"],
                json.dumps(payload),
                qos=0,
                retain=True,  # Retain system stats
            )

            return result.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error("Error publishing system stats to MQTT: %s", e)
            return False

    async def _publish_status(self, status: str) -> bool:
        """Publish service status to MQTT.

        Args:
            status: Status string (online/offline)

        Returns:
            True if published successfully, False otherwise
        """
        if not self.client:
            return False

        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "status": status,
                "client_id": self.client_id,
            }

            result = self.client.publish(
                self.topics["status"],
                json.dumps(payload),
                qos=1,
                retain=True,  # Retain status
            )

            return result.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error("Error publishing status to MQTT: %s", e)
            return False

    async def _publish_system_info(self) -> bool:
        """Publish system information to MQTT."""
        if not self._can_publish():
            return False

        try:
            import platform

            import psutil

            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "system": {
                    "platform": platform.system(),
                    "platform_release": platform.release(),
                    "architecture": platform.machine(),
                    "hostname": platform.node(),
                    "python_version": platform.python_version(),
                },
                "hardware": {
                    "cpu_count": psutil.cpu_count(),
                    "memory_total": psutil.virtual_memory().total,
                },
                "mqtt": {
                    "topic_prefix": self.topic_prefix,
                    "client_id": self.client_id,
                },
            }

            result = self.client.publish(
                self.topics["config"],
                json.dumps(payload),
                qos=1,
                retain=True,  # Retain system info
            )

            return result.rc == mqtt.MQTT_ERR_SUCCESS

        except Exception as e:
            logger.error("Error publishing system info to MQTT: %s", e)
            return False

    def _can_publish(self) -> bool:
        """Check if MQTT publishing is possible."""
        return self.enable_mqtt and self.client is not None and self.is_connected

    def get_connection_status(self) -> dict[str, Any]:
        """Get MQTT connection status information."""
        return {
            "enabled": self.enable_mqtt,
            "connected": self.is_connected,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "client_id": self.client_id,
            "topic_prefix": self.topic_prefix,
            "retry_count": self.connection_retry_count,
            "topics": self.topics,
        }
