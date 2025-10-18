"""Apprise service for multi-channel notifications.

This service uses the Apprise library to send notifications to various
platforms including email, Discord, Slack, Telegram, and many others.
"""

import asyncio
import logging
from typing import Any

import apprise

from birdnetpi.detections.models import Detection

logger = logging.getLogger(__name__)


class AppriseService:
    """Service for sending notifications through Apprise."""

    def __init__(self, enable_apprise: bool = True) -> None:
        """Initialize Apprise service.

        Args:
            enable_apprise: Whether Apprise notifications are enabled globally
        """
        self.enable_apprise = enable_apprise
        self.apprise_obj = apprise.Apprise() if enable_apprise else None
        self.targets: dict[str, list[str]] = {}  # name -> list of URLs
        self.stats = {
            "total_sent": 0,
            "total_failed": 0,
            "targets_count": 0,
        }

    async def start(self) -> None:
        """Start the Apprise service."""
        if not self.enable_apprise:
            logger.info("Apprise service disabled")
            return

        logger.info("Starting Apprise service...")
        logger.info("Apprise service started with %d configured targets", len(self.targets))

    async def stop(self) -> None:
        """Stop the Apprise service."""
        if not self.enable_apprise:
            return

        logger.info("Stopping Apprise service...")

        if self.apprise_obj:
            self.apprise_obj.clear()

        logger.info("Apprise service stopped")

    def configure_targets(self, apprise_targets: dict[str, str]) -> None:
        """Configure Apprise targets from configuration.

        Args:
            apprise_targets: Dictionary mapping target names to Apprise URLs
        """
        if self.apprise_obj is None:
            return

        self.targets.clear()
        self.apprise_obj.clear()

        for name, url in apprise_targets.items():
            if url.strip():  # Skip empty URLs
                try:
                    # Add URL to Apprise
                    if self.apprise_obj.add(url.strip(), tag=name):
                        self.targets[name] = [url.strip()]
                        logger.info("Added Apprise target: %s", name)
                    else:
                        logger.error("Failed to add Apprise target '%s': Invalid URL format", name)
                except Exception as e:
                    logger.error("Error adding Apprise target '%s': %s", name, e)

        self.stats["targets_count"] = len(self.targets)

    async def send_notification(
        self,
        title: str,
        body: str,
        target_name: str | None = None,
        notification_type: apprise.NotifyType = apprise.NotifyType.INFO,
        attach: Any | None = None,  # noqa: ANN401
    ) -> bool:
        """Send a notification through Apprise.

        Args:
            title: Notification title
            body: Notification body/message
            target_name: Optional specific target name (tag). If None, sends to all targets.
            notification_type: Type of notification (INFO, SUCCESS, WARNING, FAILURE)
            attach: Optional Apprise attachment (type varies by Apprise version)

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self._can_send():
            return False

        try:
            # Run Apprise notify in a thread pool to avoid blocking
            result = await asyncio.to_thread(
                self.apprise_obj.notify,  # type: ignore
                body=body,
                title=title,
                notify_type=notification_type,
                tag=target_name,
                attach=attach,
            )

            if result:
                self.stats["total_sent"] += 1
                logger.debug(
                    "Apprise notification sent successfully: %s (target: %s)",
                    title,
                    target_name or "all",
                )
                return True
            else:
                self.stats["total_failed"] += 1
                logger.warning(
                    "Apprise notification failed: %s (target: %s)", title, target_name or "all"
                )
                return False

        except Exception as e:
            self.stats["total_failed"] += 1
            logger.error("Error sending Apprise notification: %s", e)
            return False

    async def send_detection_notification(
        self,
        detection: Detection,
        title: str,
        body: str,
        target_name: str | None = None,
    ) -> bool:
        """Send a detection notification through Apprise.

        Args:
            detection: Detection object (for potential attachments in future)
            title: Notification title (should be rendered template)
            body: Notification body (should be rendered template)
            target_name: Optional specific target name

        Returns:
            True if notification was sent successfully, False otherwise
        """
        return await self.send_notification(
            title=title,
            body=body,
            target_name=target_name,
            notification_type=apprise.NotifyType.INFO,
        )

    async def test_target(self, target_name: str) -> dict[str, Any]:
        """Test an Apprise target by sending a test notification.

        Args:
            target_name: Name of the target to test

        Returns:
            Test result information
        """
        if self.apprise_obj is None:
            return {"success": False, "error": "Apprise service not started"}

        if target_name not in self.targets:
            return {"success": False, "error": f"Target '{target_name}' not found"}

        try:
            success = await self.send_notification(
                title="BirdNET-Pi Test Notification",
                body=(
                    "This is a test notification from BirdNET-Pi. "
                    "If you received this, your Apprise target is configured correctly."
                ),
                target_name=target_name,
                notification_type=apprise.NotifyType.INFO,
            )

            return {
                "success": success,
                "target": target_name,
                "message": "Test notification sent" if success else "Test notification failed",
            }

        except Exception as e:
            return {
                "success": False,
                "target": target_name,
                "error": str(e),
            }

    def _can_send(self) -> bool:
        """Check if notifications can be sent."""
        return self.enable_apprise and self.apprise_obj is not None and bool(self.targets)

    def get_service_status(self) -> dict[str, Any]:
        """Get Apprise service status and statistics."""
        return {
            "enabled": self.enable_apprise,
            "targets_count": len(self.targets),
            "targets": list(self.targets.keys()),
            "statistics": self.stats.copy(),
        }
