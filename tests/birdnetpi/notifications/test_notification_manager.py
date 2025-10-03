import asyncio
import json
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.notifications.manager import NotificationManager
from birdnetpi.notifications.signals import detection_signal


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance for testing."""
    config = Mock(spec=BirdNETConfig)
    config.notification_rules = []  # New notification structure
    return config


@pytest.fixture
def mock_active_websockets():
    """Provide a mock set of active websockets."""
    return set()


@pytest.fixture
def notification_manager(mock_active_websockets, test_config):
    """Provide a NotificationManager instance for testing."""
    service = NotificationManager(active_websockets=mock_active_websockets, config=test_config)
    service.register_listeners()  # Listeners
    return service


def test_handle_detection_event_basic(notification_manager, caplog, model_factory):
    """Should log a basic notification message for detection event."""
    with caplog.at_level(logging.INFO):
        detection = model_factory.create_detection(
            species_tensor="Turdus merula_Common Blackbird",
            scientific_name="Turdus merula",
            common_name="Common Blackbird",
            confidence=0.95,
        )
        notification_manager.active_websockets.add(Mock())  # Add a mock websocket
        notification_manager._handle_detection_event(None, detection)
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )


def test_handle_detection_event__notification_rules_enabled(
    test_config, notification_manager, caplog, model_factory
):
    """Should log a notification message when rules are configured for detection event."""
    test_config.notification_rules = [
        {
            "name": "All Detections",
            "enabled": True,
            "frequency": {"when": "immediate"},
        }
    ]
    with caplog.at_level(logging.INFO):
        detection = model_factory.create_detection(
            species_tensor="Erithacus rubecula_European Robin",
            scientific_name="Erithacus rubecula",
            common_name="European Robin",
            confidence=0.88,
        )
        notification_manager.active_websockets.add(Mock())  # Add a mock websocket
        notification_manager._handle_detection_event(None, detection)
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )
        assert "Simulating sending notification for rule 'All Detections'" in caplog.text


class TestWebSocketManagement:
    """Test WebSocket connection management."""

    def test_add_websocket(self, notification_manager, caplog):
        """Should add websocket to active connections."""
        mock_ws = Mock()

        with caplog.at_level(logging.INFO):
            notification_manager.add_websocket(mock_ws)

        assert mock_ws in notification_manager.active_websockets
        assert "WebSocket added to active connections. Total: 1" in caplog.text

    def test_add_multiple_websockets(self, notification_manager):
        """Should handle multiple websocket connections."""
        ws1 = Mock()
        ws2 = Mock()
        ws3 = Mock()

        notification_manager.add_websocket(ws1)
        notification_manager.add_websocket(ws2)
        notification_manager.add_websocket(ws3)

        assert len(notification_manager.active_websockets) == 3
        assert all(ws in notification_manager.active_websockets for ws in [ws1, ws2, ws3])

    def test_remove_websocket(self, notification_manager, caplog):
        """Should remove websocket from active connections."""
        mock_ws = Mock()
        notification_manager.add_websocket(mock_ws)

        with caplog.at_level(logging.INFO):
            notification_manager.remove_websocket(mock_ws)

        assert mock_ws not in notification_manager.active_websockets
        assert "WebSocket removed from active connections. Total: 0" in caplog.text

    def test_remove_non_existent_websocket(self, notification_manager):
        """Should handle removing non-existent websocket gracefully."""
        mock_ws = Mock()
        # Should not raise error
        notification_manager.remove_websocket(mock_ws)
        assert len(notification_manager.active_websockets) == 0


class TestAsyncNotifications:
    """Test async notification sending."""

    @pytest.mark.asyncio
    async def test_send_websocket_notifications(self, notification_manager, model_factory):
        """Should send notifications to all connected websockets."""
        # Create mock websockets with async send methods
        ws1 = Mock()
        ws1.send_text = AsyncMock()
        ws2 = Mock()
        ws2.send_text = AsyncMock()

        notification_manager.add_websocket(ws1)
        notification_manager.add_websocket(ws2)

        detection = model_factory.create_detection(
            species_tensor="Parus major_Great Tit",
            scientific_name="Parus major",
            common_name="Great Tit",
            confidence=0.92,
        )

        await notification_manager._send_websocket_notifications(detection)

        # Both websockets should receive the notification
        expected_data = {
            "type": "detection",
            "detection": {
                "species": "Great Tit",
                "common_name": "Great Tit",
                "scientific_name": "Parus major",
                "confidence": 0.92,
                "datetime": detection.timestamp.isoformat() if detection.timestamp else None,
            },
        }
        expected_json = json.dumps(expected_data)

        ws1.send_text.assert_called_once_with(expected_json)
        ws2.send_text.assert_called_once_with(expected_json)

    @pytest.mark.asyncio
    async def test_send_websocket_notifications_with_disconnected(
        self, notification_manager, caplog, model_factory
    ):
        """Should handle disconnected websockets gracefully."""
        # Create mock websocket that raises exception on send
        ws_disconnected = Mock()
        ws_disconnected.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        ws_active = Mock()
        ws_active.send_text = AsyncMock()

        notification_manager.add_websocket(ws_disconnected)
        notification_manager.add_websocket(ws_active)

        detection = model_factory.create_detection(
            species_tensor="Corvus corax_Common Raven",
            scientific_name="Corvus corax",
            common_name="Common Raven",
            confidence=0.85,
        )

        with caplog.at_level(logging.WARNING):
            await notification_manager._send_websocket_notifications(detection)

        # Should log warning for failed websocket
        assert "Failed to send WebSocket notification" in caplog.text
        # But should still send to active websocket
        ws_active.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_iot_notifications_mqtt(self, notification_manager, model_factory):
        """Should send MQTT notifications when service is available."""
        mock_mqtt = Mock()
        mock_mqtt.publish_detection = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        detection = model_factory.create_detection(
            species_tensor="Strix aluco_Tawny Owl",
            scientific_name="Strix aluco",
            common_name="Tawny Owl",
            confidence=0.78,
        )

        await notification_manager._send_iot_notifications(detection)

        mock_mqtt.publish_detection.assert_called_once_with(detection)

    @pytest.mark.asyncio
    async def test_send_iot_notifications_webhook(self, notification_manager, model_factory):
        """Should send webhook notifications when service is available."""
        mock_webhook = Mock()
        mock_webhook.send_detection_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        detection = model_factory.create_detection(
            species_tensor="Falco peregrinus_Peregrine Falcon",
            scientific_name="Falco peregrinus",
            common_name="Peregrine Falcon",
            confidence=0.89,
        )

        await notification_manager._send_iot_notifications(detection)

        mock_webhook.send_detection_webhook.assert_called_once_with(detection)

    @pytest.mark.asyncio
    async def test_send_iot_notifications_both_services(self, notification_manager, model_factory):
        """Should send both MQTT and webhook notifications when both services available."""
        mock_mqtt = Mock()
        mock_mqtt.publish_detection = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = Mock()
        mock_webhook.send_detection_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        detection = model_factory.create_detection(
            species_tensor="Aquila chrysaetos_Golden Eagle",
            scientific_name="Aquila chrysaetos",
            common_name="Golden Eagle",
            confidence=0.95,
        )

        await notification_manager._send_iot_notifications(detection)

        mock_mqtt.publish_detection.assert_called_once_with(detection)
        mock_webhook.send_detection_webhook.assert_called_once_with(detection)


class TestNotificationRules:
    """Test notification rule processing."""

    def test_immediate_notification_rule(
        self, test_config, notification_manager, caplog, model_factory
    ):
        """Should process immediate notification rules."""
        test_config.notification_rules = [
            {
                "name": "High Confidence",
                "enabled": True,
                "frequency": {"when": "immediate"},
                "filters": {"confidence_min": 0.9},
            }
        ]

        detection = model_factory.create_detection(
            species_tensor="Buteo buteo_Common Buzzard",
            scientific_name="Buteo buteo",
            common_name="Common Buzzard",
            confidence=0.93,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        assert "Simulating sending notification for rule 'High Confidence'" in caplog.text

    def test_disabled_notification_rule(
        self, test_config, notification_manager, caplog, model_factory
    ):
        """Should skip disabled notification rules."""
        test_config.notification_rules = [
            {
                "name": "Disabled Rule",
                "enabled": False,
                "frequency": {"when": "immediate"},
            }
        ]

        detection = model_factory.create_detection(
            species_tensor="Pica pica_Eurasian Magpie",
            scientific_name="Pica pica",
            common_name="Eurasian Magpie",
            confidence=0.87,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        assert "Simulating sending notification" not in caplog.text

    def test_scheduled_notification_rule(
        self, test_config, notification_manager, caplog, model_factory
    ):
        """Should skip non-immediate notification rules."""
        test_config.notification_rules = [
            {
                "name": "Daily Summary",
                "enabled": True,
                "frequency": {"when": "scheduled", "times": ["08:00", "20:00"]},
            }
        ]

        detection = model_factory.create_detection(
            species_tensor="Columba palumbus_Common Wood Pigeon",
            scientific_name="Columba palumbus",
            common_name="Common Wood Pigeon",
            confidence=0.82,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        # Should not send scheduled notifications on detection event
        assert "Simulating sending notification" not in caplog.text

    def test_multiple_notification_rules(
        self, test_config, notification_manager, caplog, model_factory
    ):
        """Should process only the first matching immediate rule."""
        test_config.notification_rules = [
            {
                "name": "Rule 1",
                "enabled": True,
                "frequency": {"when": "immediate"},
            },
            {
                "name": "Rule 2",
                "enabled": True,
                "frequency": {"when": "immediate"},
            },
        ]

        detection = model_factory.create_detection(
            species_tensor="Regulus regulus_Goldcrest",
            scientific_name="Regulus regulus",
            common_name="Goldcrest",
            confidence=0.79,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        # Should only process first rule (has break statement)
        assert "Simulating sending notification for rule 'Rule 1'" in caplog.text
        assert "Simulating sending notification for rule 'Rule 2'" not in caplog.text


class TestEventLoopHandling:
    """Test event loop handling for async operations."""

    def test_handle_detection_without_event_loop(self, notification_manager, caplog, model_factory):
        """Should handle detection events when no event loop is running."""
        detection = model_factory.create_detection(
            species_tensor="Phoenicurus ochruros_Black Redstart",
            scientific_name="Phoenicurus ochruros",
            common_name="Black Redstart",
            confidence=0.76,
        )

        # Add websocket to trigger async code path
        notification_manager.add_websocket(Mock())

        with caplog.at_level(logging.DEBUG):
            # This runs in sync context (no event loop)
            notification_manager._handle_detection_event(None, detection)

        # Should log that async operations were skipped
        assert "No event loop running" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_detection_with_event_loop(self, notification_manager, model_factory):
        """Should handle detection events when event loop is running."""
        # Create mock websocket
        ws = Mock()
        ws.send_text = AsyncMock()
        notification_manager.add_websocket(ws)

        detection = model_factory.create_detection(
            species_tensor="Motacilla alba_White Wagtail",
            scientific_name="Motacilla alba",
            common_name="White Wagtail",
            confidence=0.84,
        )

        # This runs in async context (has event loop)
        notification_manager._handle_detection_event(None, detection)

        # Give async tasks time to complete
        await asyncio.sleep(0.1)

        # WebSocket should have received notification
        ws.send_text.assert_called_once()


class TestSignalRegistration:
    """Test signal registration."""

    def test_register_listeners(self, mock_active_websockets, test_config, caplog):
        """Should register detection signal listeners."""
        # Create new manager (without auto-registration)
        manager = NotificationManager(mock_active_websockets, test_config)

        # Verify no listeners before registration
        initial_receivers = len(detection_signal.receivers)

        with caplog.at_level(logging.INFO):
            manager.register_listeners()

        assert "NotificationManager listeners registered" in caplog.text

        # Verify listener was added
        assert len(detection_signal.receivers) > initial_receivers


class TestSystemNotifications:
    """Test system-level notification methods."""

    @pytest.mark.asyncio
    async def test_send_system_health_notification(self, notification_manager):
        """Should send system health notifications to all configured services."""
        # Setup mock services
        mock_mqtt = Mock()
        mock_mqtt.publish_system_health = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = Mock()
        mock_webhook.send_health_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        health_data = {
            "cpu_usage": 45.2,
            "memory_usage": 67.8,
            "disk_usage": 34.5,
            "temperature": 52.3,
        }

        await notification_manager.send_system_health_notification(health_data)

        # Verify both services were called
        mock_mqtt.publish_system_health.assert_called_once_with(health_data)
        mock_webhook.send_health_webhook.assert_called_once_with(health_data)

    @pytest.mark.asyncio
    async def test_send_system_health_notification_no_services(self, notification_manager):
        """Should handle gracefully when no services are configured."""
        # No services configured
        notification_manager.mqtt_service = None
        notification_manager.webhook_service = None

        health_data = {"cpu_usage": 45.2}

        # Should not raise any errors
        await notification_manager.send_system_health_notification(health_data)

    @pytest.mark.asyncio
    async def test_send_system_health_notification_with_error(self, notification_manager, caplog):
        """Should log error when system health notification fails."""
        mock_mqtt = Mock()
        mock_mqtt.publish_system_health = AsyncMock(side_effect=Exception("MQTT connection failed"))
        notification_manager.mqtt_service = mock_mqtt

        health_data = {"cpu_usage": 45.2}

        with caplog.at_level(logging.ERROR):
            await notification_manager.send_system_health_notification(health_data)

        assert "Error sending system health IoT notifications" in caplog.text
        assert "MQTT connection failed" in caplog.text

    @pytest.mark.asyncio
    async def test_send_gps_notification(self, notification_manager):
        """Should send GPS notifications to all configured services."""
        # Setup mock services
        mock_mqtt = Mock()
        mock_mqtt.publish_gps_location = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = Mock()
        mock_webhook.send_gps_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        latitude = 51.5074
        longitude = -0.1278
        accuracy = 10.5

        await notification_manager.send_gps_notification(latitude, longitude, accuracy)

        # Verify both services were called with correct parameters
        mock_mqtt.publish_gps_location.assert_called_once_with(latitude, longitude, accuracy)
        mock_webhook.send_gps_webhook.assert_called_once_with(latitude, longitude, accuracy)

    @pytest.mark.asyncio
    async def test_send_gps_notification_without_accuracy(self, notification_manager):
        """Should send GPS notifications without accuracy parameter."""
        mock_mqtt = Mock()
        mock_mqtt.publish_gps_location = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        latitude = 40.7128
        longitude = -74.0060

        await notification_manager.send_gps_notification(latitude, longitude)

        # Should be called with None for accuracy
        mock_mqtt.publish_gps_location.assert_called_once_with(latitude, longitude, None)

    @pytest.mark.asyncio
    async def test_send_gps_notification_with_error(self, notification_manager, caplog):
        """Should log error when GPS notification fails."""
        mock_webhook = Mock()
        mock_webhook.send_gps_webhook = AsyncMock(side_effect=Exception("Webhook timeout"))
        notification_manager.webhook_service = mock_webhook

        with caplog.at_level(logging.ERROR):
            await notification_manager.send_gps_notification(48.8566, 2.3522)

        assert "Error sending GPS IoT notifications" in caplog.text
        assert "Webhook timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_send_system_stats_notification(self, notification_manager):
        """Should send system stats notifications to all configured services."""
        # Setup mock services
        mock_mqtt = Mock()
        mock_mqtt.publish_system_stats = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = Mock()
        mock_webhook.send_system_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        stats_data = {
            "detection_count": 150,
            "species_count": 25,
            "uptime": 86400,
            "last_detection": "2024-01-01T12:00:00",
        }

        await notification_manager.send_system_stats_notification(stats_data)

        # Verify both services were called
        mock_mqtt.publish_system_stats.assert_called_once_with(stats_data)
        mock_webhook.send_system_webhook.assert_called_once_with(stats_data)

    @pytest.mark.asyncio
    async def test_send_system_stats_notification_mqtt_only(self, notification_manager):
        """Should send system stats to MQTT only when webhook not configured."""
        mock_mqtt = Mock()
        mock_mqtt.publish_system_stats = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt
        notification_manager.webhook_service = None

        stats_data = {"detection_count": 100}

        await notification_manager.send_system_stats_notification(stats_data)

        mock_mqtt.publish_system_stats.assert_called_once_with(stats_data)

    @pytest.mark.asyncio
    async def test_send_system_stats_notification_with_error(self, notification_manager, caplog):
        """Should log error when system stats notification fails."""
        mock_mqtt = Mock()
        mock_mqtt.publish_system_stats = AsyncMock(side_effect=Exception("Connection refused"))
        notification_manager.mqtt_service = mock_mqtt

        with caplog.at_level(logging.ERROR):
            await notification_manager.send_system_stats_notification({"uptime": 3600})

        assert "Error sending system stats IoT notifications" in caplog.text
        assert "Connection refused" in caplog.text


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_send_websocket_notifications_empty_set(
        self, notification_manager, model_factory
    ):
        """Should return early when no websockets are connected."""
        # Ensure websockets set is empty
        notification_manager.active_websockets.clear()

        detection = model_factory.create_detection(
            species_tensor="Test species",
            scientific_name="Testicus species",
            common_name="Test Bird",
            confidence=0.5,
        )

        # Should return without doing anything (line 92)
        await notification_manager._send_websocket_notifications(detection)
        # No assertions needed - just ensuring line 92 is covered

    @pytest.mark.asyncio
    async def test_send_iot_notifications_error_handling(
        self, notification_manager, caplog, model_factory
    ):
        """Should handle and log errors in IoT notifications."""
        # Setup service that raises an exception
        mock_mqtt = Mock()
        mock_mqtt.publish_detection = AsyncMock(side_effect=Exception("Network error"))
        notification_manager.mqtt_service = mock_mqtt

        detection = model_factory.create_detection(
            species_tensor="Error test",
            scientific_name="Erroricus testicus",
            common_name="Error Bird",
            confidence=0.5,
        )

        with caplog.at_level(logging.ERROR):
            await notification_manager._send_iot_notifications(detection)

        # Should log the error (lines 138-141)
        assert "Error sending IoT notifications" in caplog.text
        assert "Network error" in caplog.text
        assert detection.get_display_name() in caplog.text
