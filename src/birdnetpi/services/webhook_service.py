"""Webhook service for HTTP-based integrations and notifications.

This service sends HTTP POST requests to configured webhook URLs when
detection events occur, providing integration with external systems.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from birdnetpi.models.database_models import Detection

logger = logging.getLogger(__name__)


class WebhookConfig:
    """Configuration for a webhook endpoint."""

    def __init__(
        self,
        url: str,
        name: str = "",
        headers: dict[str, str] | None = None,
        enabled: bool = True,
        timeout: int = 10,
        retry_count: int = 3,
        events: list[str] | None = None,
    ) -> None:
        """Initialize webhook configuration.

        Args:
            url: Webhook URL to send POST requests to
            name: Optional descriptive name for the webhook
            headers: Optional HTTP headers to include
            enabled: Whether this webhook is enabled
            timeout: Request timeout in seconds
            retry_count: Number of retry attempts on failure
            events: List of event types to send (default: all)
        """
        self.url = url
        self.name = name or self._extract_name_from_url(url)
        self.headers = headers or {}
        self.enabled = enabled
        self.timeout = timeout
        self.retry_count = retry_count
        self.events = events or ["detection", "health", "gps", "system"]

        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid webhook URL: {url}")

    def _extract_name_from_url(self, url: str) -> str:
        """Extract a name from the webhook URL."""
        parsed = urlparse(url)
        return parsed.netloc or "webhook"

    def should_send_event(self, event_type: str) -> bool:
        """Check if this webhook should receive the given event type."""
        return self.enabled and event_type in self.events


class WebhookService:
    """Service for sending webhook notifications."""

    def __init__(self, enable_webhooks: bool = False) -> None:
        """Initialize webhook service.

        Args:
            enable_webhooks: Whether webhook sending is enabled globally
        """
        self.enable_webhooks = enable_webhooks
        self.webhooks: list[WebhookConfig] = []
        self.client: httpx.AsyncClient | None = None
        self.stats = {
            "total_sent": 0,
            "total_failed": 0,
            "webhooks_count": 0,
        }

    async def start(self) -> None:
        """Start the webhook service."""
        if not self.enable_webhooks:
            logger.info("Webhook service disabled")
            return

        logger.info("Starting webhook service...")

        # Create HTTP client with reasonable defaults
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        logger.info("Webhook service started with %d configured webhooks", len(self.webhooks))

    async def stop(self) -> None:
        """Stop the webhook service."""
        if not self.enable_webhooks:
            return

        logger.info("Stopping webhook service...")

        if self.client:
            await self.client.aclose()
            self.client = None

        logger.info("Webhook service stopped")

    def add_webhook(self, webhook_config: WebhookConfig) -> None:
        """Add a webhook configuration.

        Args:
            webhook_config: Webhook configuration to add
        """
        self.webhooks.append(webhook_config)
        self.stats["webhooks_count"] = len(self.webhooks)
        logger.info("Added webhook: %s (%s)", webhook_config.name, webhook_config.url)

    def remove_webhook(self, url: str) -> bool:
        """Remove a webhook configuration by URL.

        Args:
            url: URL of the webhook to remove

        Returns:
            True if webhook was removed, False if not found
        """
        for i, webhook in enumerate(self.webhooks):
            if webhook.url == url:
                removed = self.webhooks.pop(i)
                self.stats["webhooks_count"] = len(self.webhooks)
                logger.info("Removed webhook: %s (%s)", removed.name, removed.url)
                return True
        return False

    def configure_webhooks_from_urls(self, webhook_urls: list[str]) -> None:
        """Configure webhooks from a list of URLs.

        Args:
            webhook_urls: List of webhook URLs to configure
        """
        self.webhooks.clear()

        for url in webhook_urls:
            if url.strip():  # Skip empty URLs
                try:
                    webhook_config = WebhookConfig(url.strip())
                    self.add_webhook(webhook_config)
                except ValueError as e:
                    logger.error("Invalid webhook URL '%s': %s", url, e)

    async def send_detection_webhook(self, detection: Detection) -> None:
        """Send detection event to configured webhooks.

        Args:
            detection: Detection object to send
        """
        if not self._can_send():
            return

        payload = {
            "event_type": "detection",
            "timestamp": datetime.now(UTC).isoformat(),
            "detection": {
                "id": detection.id,
                "timestamp": detection.timestamp.isoformat(),
                "species": detection.get_display_name(),
                "confidence": detection.confidence,
                "location": {
                    "latitude": detection.latitude,
                    "longitude": detection.longitude,
                }
                if detection.latitude is not None and detection.longitude is not None
                else None,
                "analysis": {
                    "species_confidence_threshold": detection.species_confidence_threshold,
                    "week": detection.week,
                    "sensitivity_setting": detection.sensitivity_setting,
                    "overlap": detection.overlap,
                },
            },
        }

        await self._send_to_webhooks("detection", payload)

    async def send_health_webhook(self, health_data: dict[str, Any]) -> None:
        """Send system health event to configured webhooks.

        Args:
            health_data: System health information
        """
        if not self._can_send():
            return

        payload = {
            "event_type": "health",
            "timestamp": datetime.now(UTC).isoformat(),
            "health": health_data,
        }

        await self._send_to_webhooks("health", payload)

    async def send_gps_webhook(
        self, latitude: float, longitude: float, accuracy: float | None = None
    ) -> None:
        """Send GPS location event to configured webhooks.

        Args:
            latitude: GPS latitude
            longitude: GPS longitude
            accuracy: Optional GPS accuracy in meters
        """
        if not self._can_send():
            return

        payload = {
            "event_type": "gps",
            "timestamp": datetime.now(UTC).isoformat(),
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
            },
        }

        await self._send_to_webhooks("gps", payload)

    async def send_system_webhook(self, system_data: dict[str, Any]) -> None:
        """Send system statistics event to configured webhooks.

        Args:
            system_data: System statistics and information
        """
        if not self._can_send():
            return

        payload = {
            "event_type": "system",
            "timestamp": datetime.now(UTC).isoformat(),
            "system": system_data,
        }

        await self._send_to_webhooks("system", payload)

    async def _send_to_webhooks(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send event payload to all relevant webhooks.

        Args:
            event_type: Type of event being sent
            payload: Event payload to send
        """
        if not self.client:
            return

        # Filter webhooks that should receive this event type
        relevant_webhooks = [
            webhook for webhook in self.webhooks if webhook.should_send_event(event_type)
        ]

        if not relevant_webhooks:
            logger.debug("No webhooks configured for event type: %s", event_type)
            return

        # Send to all relevant webhooks concurrently
        tasks = [self._send_webhook_request(webhook, payload) for webhook in relevant_webhooks]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log results
        successful = sum(1 for result in results if result is True)
        failed = len(results) - successful

        self.stats["total_sent"] += successful
        self.stats["total_failed"] += failed

        logger.debug(
            "Sent %s event to %d webhooks (%d successful, %d failed)",
            event_type,
            len(relevant_webhooks),
            successful,
            failed,
        )

    async def _send_webhook_request(self, webhook: WebhookConfig, payload: dict[str, Any]) -> bool:
        """Send HTTP POST request to a single webhook.

        Args:
            webhook: Webhook configuration
            payload: Payload to send

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False

        for attempt in range(webhook.retry_count + 1):
            try:
                # Prepare headers
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "BirdNET-Pi/1.0",
                    **webhook.headers,
                }

                # Send POST request
                response = await self.client.post(
                    webhook.url,
                    json=payload,
                    headers=headers,
                    timeout=webhook.timeout,
                )

                # Check if successful
                if response.status_code < 400:
                    logger.debug(
                        "Webhook sent successfully: %s (HTTP %d)",
                        webhook.name,
                        response.status_code,
                    )
                    return True
                else:
                    logger.warning(
                        "Webhook failed: %s (HTTP %d) - %s",
                        webhook.name,
                        response.status_code,
                        response.text[:200],
                    )

            except httpx.TimeoutException:
                logger.warning(
                    "Webhook timeout (attempt %d/%d): %s",
                    attempt + 1,
                    webhook.retry_count + 1,
                    webhook.name,
                )
            except httpx.RequestError as e:
                logger.warning(
                    "Webhook request error (attempt %d/%d): %s - %s",
                    attempt + 1,
                    webhook.retry_count + 1,
                    webhook.name,
                    str(e),
                )
            except Exception as e:
                logger.error(
                    "Unexpected webhook error (attempt %d/%d): %s - %s",
                    attempt + 1,
                    webhook.retry_count + 1,
                    webhook.name,
                    str(e),
                )

            # Wait before retry (exponential backoff)
            if attempt < webhook.retry_count:
                await asyncio.sleep(2**attempt)

        logger.error("Webhook failed after %d attempts: %s", webhook.retry_count + 1, webhook.name)
        return False

    def _can_send(self) -> bool:
        """Check if webhooks can be sent."""
        return self.enable_webhooks and self.client is not None and bool(self.webhooks)

    def get_webhook_status(self) -> dict[str, Any]:
        """Get webhook service status and statistics."""
        return {
            "enabled": self.enable_webhooks,
            "webhook_count": len(self.webhooks),
            "webhooks": [
                {
                    "name": webhook.name,
                    "url": webhook.url,
                    "enabled": webhook.enabled,
                    "events": webhook.events,
                }
                for webhook in self.webhooks
            ],
            "statistics": self.stats.copy(),
        }

    async def test_webhook(self, webhook_url: str) -> dict[str, Any]:
        """Test a webhook URL by sending a test payload.

        Args:
            webhook_url: URL to test

        Returns:
            Test result information
        """
        if not self.client:
            return {"success": False, "error": "Webhook service not started"}

        try:
            # Create temporary webhook config for testing
            test_webhook = WebhookConfig(webhook_url, name="test", timeout=10)

            # Test payload
            test_payload = {
                "event_type": "test",
                "timestamp": datetime.now(UTC).isoformat(),
                "message": "This is a test webhook from BirdNET-Pi",
                "test": True,
            }

            # Send test request
            success = await self._send_webhook_request(test_webhook, test_payload)

            return {
                "success": success,
                "url": webhook_url,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            return {
                "success": False,
                "url": webhook_url,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
