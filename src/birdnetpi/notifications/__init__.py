"""Notifications domain for alerts, webhooks, messaging services, and event signals."""

from birdnetpi.notifications.birdweather import BirdWeatherService
from birdnetpi.notifications.mqtt import MQTTService
from birdnetpi.notifications.notification_manager import NotificationManager
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.notifications.webhooks import WebhookConfig, WebhookService

__all__ = [
    "BirdWeatherService",
    "MQTTService",
    "NotificationManager",
    "WebhookConfig",
    "WebhookService",
    "detection_signal",
]
