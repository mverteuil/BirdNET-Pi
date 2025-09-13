import logging
from unittest.mock import Mock

import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import Detection
from birdnetpi.notifications.manager import NotificationManager


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
def notification_manager(mock_active_websockets, mock_config):
    """Provide a NotificationManager instance for testing."""
    service = NotificationManager(active_websockets=mock_active_websockets, config=mock_config)
    service.register_listeners()  # Listeners
    return service


def test_handle_detection_event_basic(notification_manager, caplog):
    """Should log a basic notification message for detection event."""
    with caplog.at_level(logging.INFO):
        detection = Detection(
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
    mock_config, notification_manager, caplog
):
    """Should log a notification message when rules are configured for detection event."""
    mock_config.notification_rules = [
        {
            "name": "All Detections",
            "enabled": True,
            "frequency": {"when": "immediate"},
        }
    ]
    with caplog.at_level(logging.INFO):
        detection = Detection(
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
    async def test_send_websocket_notifications(self, notification_manager):
        """Should send notifications to all connected websockets."""
        import json
        from unittest.mock import AsyncMock

        # Create mock websockets with async send methods
        ws1 = Mock()
        ws1.send_text = AsyncMock()
        ws2 = Mock()
        ws2.send_text = AsyncMock()

        notification_manager.add_websocket(ws1)
        notification_manager.add_websocket(ws2)

        detection = Detection(
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
        self, notification_manager, caplog
    ):
        """Should handle disconnected websockets gracefully."""
        from unittest.mock import AsyncMock

        # Create mock websocket that raises exception on send
        ws_disconnected = Mock()
        ws_disconnected.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        ws_active = Mock()
        ws_active.send_text = AsyncMock()

        notification_manager.add_websocket(ws_disconnected)
        notification_manager.add_websocket(ws_active)

        detection = Detection(
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
    async def test_send_iot_notifications_mqtt(self, notification_manager):
        """Should send MQTT notifications when service is available."""
        from unittest.mock import AsyncMock

        mock_mqtt = Mock()
        mock_mqtt.publish_detection = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        detection = Detection(
            species_tensor="Strix aluco_Tawny Owl",
            scientific_name="Strix aluco",
            common_name="Tawny Owl",
            confidence=0.78,
        )

        await notification_manager._send_iot_notifications(detection)

        mock_mqtt.publish_detection.assert_called_once_with(detection)

    @pytest.mark.asyncio
    async def test_send_iot_notifications_webhook(self, notification_manager):
        """Should send webhook notifications when service is available."""
        from unittest.mock import AsyncMock

        mock_webhook = Mock()
        mock_webhook.send_detection_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        detection = Detection(
            species_tensor="Falco peregrinus_Peregrine Falcon",
            scientific_name="Falco peregrinus",
            common_name="Peregrine Falcon",
            confidence=0.89,
        )

        await notification_manager._send_iot_notifications(detection)

        mock_webhook.send_detection_webhook.assert_called_once_with(detection)

    @pytest.mark.asyncio
    async def test_send_iot_notifications_both_services(self, notification_manager):
        """Should send both MQTT and webhook notifications when both services available."""
        from unittest.mock import AsyncMock

        mock_mqtt = Mock()
        mock_mqtt.publish_detection = AsyncMock()
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = Mock()
        mock_webhook.send_detection_webhook = AsyncMock()
        notification_manager.webhook_service = mock_webhook

        detection = Detection(
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

    def test_immediate_notification_rule(self, mock_config, notification_manager, caplog):
        """Should process immediate notification rules."""
        mock_config.notification_rules = [
            {
                "name": "High Confidence",
                "enabled": True,
                "frequency": {"when": "immediate"},
                "filters": {"confidence_min": 0.9},
            }
        ]

        detection = Detection(
            species_tensor="Buteo buteo_Common Buzzard",
            scientific_name="Buteo buteo",
            common_name="Common Buzzard",
            confidence=0.93,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        assert "Simulating sending notification for rule 'High Confidence'" in caplog.text

    def test_disabled_notification_rule(self, mock_config, notification_manager, caplog):
        """Should skip disabled notification rules."""
        mock_config.notification_rules = [
            {
                "name": "Disabled Rule",
                "enabled": False,
                "frequency": {"when": "immediate"},
            }
        ]

        detection = Detection(
            species_tensor="Pica pica_Eurasian Magpie",
            scientific_name="Pica pica",
            common_name="Eurasian Magpie",
            confidence=0.87,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        assert "Simulating sending notification" not in caplog.text

    def test_scheduled_notification_rule(self, mock_config, notification_manager, caplog):
        """Should skip non-immediate notification rules."""
        mock_config.notification_rules = [
            {
                "name": "Daily Summary",
                "enabled": True,
                "frequency": {"when": "scheduled", "times": ["08:00", "20:00"]},
            }
        ]

        detection = Detection(
            species_tensor="Columba palumbus_Common Wood Pigeon",
            scientific_name="Columba palumbus",
            common_name="Common Wood Pigeon",
            confidence=0.82,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        # Should not send scheduled notifications on detection event
        assert "Simulating sending notification" not in caplog.text

    def test_multiple_notification_rules(self, mock_config, notification_manager, caplog):
        """Should process only the first matching immediate rule."""
        mock_config.notification_rules = [
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

        detection = Detection(
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

    def test_handle_detection_without_event_loop(self, notification_manager, caplog):
        """Should handle detection events when no event loop is running."""
        detection = Detection(
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
    async def test_handle_detection_with_event_loop(self, notification_manager):
        """Should handle detection events when event loop is running."""
        import asyncio
        from unittest.mock import AsyncMock

        # Create mock websocket
        ws = Mock()
        ws.send_text = AsyncMock()
        notification_manager.add_websocket(ws)

        detection = Detection(
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

    def test_register_listeners(self, mock_active_websockets, mock_config, caplog):
        """Should register detection signal listeners."""
        from birdnetpi.notifications.signals import detection_signal

        # Create new manager (without auto-registration)
        manager = NotificationManager(mock_active_websockets, mock_config)

        # Verify no listeners before registration
        initial_receivers = len(detection_signal.receivers)

        with caplog.at_level(logging.INFO):
            manager.register_listeners()

        assert "NotificationManager listeners registered" in caplog.text

        # Verify listener was added
        assert len(detection_signal.receivers) > initial_receivers
