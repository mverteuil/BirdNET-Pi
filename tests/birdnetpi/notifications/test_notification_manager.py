"""Tests for notification manager."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.websockets import WebSocket

from birdnetpi.config import BirdNETConfig
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.manager import NotificationManager
from birdnetpi.notifications.mqtt import MQTTService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.notifications.webhooks import WebhookService


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
def mock_species_database(path_resolver):
    """Provide a SpeciesDatabaseService for testing."""
    # Create real service with path resolver pointing to test databases
    return SpeciesDatabaseService(path_resolver)


@pytest.fixture
def notification_manager(
    mock_active_websockets, test_config, db_service_factory, mock_species_database
):
    """Provide a NotificationManager instance for testing."""
    # Use the global db_service_factory pattern
    mock_core_database, _session, _result = db_service_factory()

    # Mock detection query service
    mock_detection_query_service = Mock(spec=DetectionQueryService)
    mock_detection_query_service.is_first_detection_ever = AsyncMock(
        spec=AsyncMock, return_value=True
    )
    mock_detection_query_service.is_first_detection_in_period = AsyncMock(
        spec=AsyncMock, return_value=True
    )

    service = NotificationManager(
        active_websockets=mock_active_websockets,
        config=test_config,
        core_database=mock_core_database,
        species_db_service=mock_species_database,
        detection_query_service=mock_detection_query_service,
    )
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
        notification_manager.active_websockets.add(Mock(spec=WebSocket))  # Add a mock websocket
        notification_manager._handle_detection_event(None, detection)
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )


def test_handle_detection_event__notification_rules_enabled(
    test_config, notification_manager, caplog, model_factory
):
    """Should process notification rules when configured for detection event."""
    test_config.notification_rules = [
        {
            "name": "All Detections",
            "enabled": True,
            "frequency": {"when": "immediate"},
            "service": "apprise",
            "target": "test",
            "scope": "all",
        }
    ]
    with caplog.at_level(logging.INFO):
        detection = model_factory.create_detection(
            species_tensor="Erithacus rubecula_European Robin",
            scientific_name="Erithacus rubecula",
            common_name="European Robin",
            confidence=0.88,
        )
        notification_manager.active_websockets.add(Mock(spec=WebSocket))  # Add a mock websocket
        notification_manager._handle_detection_event(None, detection)
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )
        # Note: Actual notification processing happens asynchronously
        # The test framework would need to be async to fully test this


class TestWebSocketManagement:
    """Test WebSocket connection management."""

    @pytest.mark.parametrize(
        "websocket_count,expected_count",
        [
            pytest.param(1, 1, id="single-websocket"),
            pytest.param(3, 3, id="multiple-websockets"),
        ],
    )
    def test_add_websockets(self, notification_manager, caplog, websocket_count, expected_count):
        """Should add websocket(s) to active connections."""
        websockets = [Mock(spec=WebSocket) for _ in range(websocket_count)]

        with caplog.at_level(logging.INFO):
            for ws in websockets:
                notification_manager.add_websocket(ws)

        assert len(notification_manager.active_websockets) == expected_count
        assert all(ws in notification_manager.active_websockets for ws in websockets)
        if websocket_count == 1:
            assert f"WebSocket added to active connections. Total: {expected_count}" in caplog.text

    def test_remove_websocket(self, notification_manager, caplog):
        """Should remove websocket from active connections."""
        mock_ws = Mock(spec=WebSocket)
        notification_manager.add_websocket(mock_ws)

        with caplog.at_level(logging.INFO):
            notification_manager.remove_websocket(mock_ws)

        assert mock_ws not in notification_manager.active_websockets
        assert "WebSocket removed from active connections. Total: 0" in caplog.text

    def test_remove_non_existent_websocket(self, notification_manager):
        """Should handle removing non-existent websocket gracefully."""
        mock_ws = Mock(spec=WebSocket)
        # Should not raise error
        notification_manager.remove_websocket(mock_ws)
        assert len(notification_manager.active_websockets) == 0


class TestAsyncNotifications:
    """Test async notification sending."""

    @pytest.mark.asyncio
    async def test_send_websocket_notifications(self, notification_manager, model_factory):
        """Should send notifications to all connected websockets."""
        # Create mock websockets with async send methods
        ws1 = Mock(spec=WebSocket)
        ws1.send_text = AsyncMock(spec=callable)
        ws2 = Mock(spec=WebSocket)
        ws2.send_text = AsyncMock(spec=callable)

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
        ws_disconnected = Mock(spec=WebSocket)
        ws_disconnected.send_text = AsyncMock(
            spec=callable, side_effect=Exception("Connection closed")
        )

        ws_active = Mock(spec=WebSocket)
        ws_active.send_text = AsyncMock(spec=callable)

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
    @pytest.mark.parametrize(
        "mqtt_available,webhook_available,detection_species",
        [
            pytest.param(True, False, "Strix aluco_Tawny Owl", id="mqtt-only"),
            pytest.param(False, True, "Falco peregrinus_Peregrine Falcon", id="webhook-only"),
            pytest.param(True, True, "Aquila chrysaetos_Golden Eagle", id="both-services"),
        ],
    )
    async def test_send_iot_notifications(
        self,
        notification_manager,
        model_factory,
        async_mock_factory,
        mqtt_available,
        webhook_available,
        detection_species,
    ):
        """Should send IoT notifications to configured services."""
        # Initialize mock variables
        mock_mqtt = None
        mock_webhook = None

        if mqtt_available:
            mock_mqtt = async_mock_factory(MQTTService, publish_detection=None)
            notification_manager.mqtt_service = mock_mqtt
        else:
            notification_manager.mqtt_service = None

        if webhook_available:
            mock_webhook = async_mock_factory(WebhookService, send_detection_webhook=None)
            notification_manager.webhook_service = mock_webhook
        else:
            notification_manager.webhook_service = None

        detection = model_factory.create_detection(
            species_tensor=detection_species,
            scientific_name=detection_species.split("_")[0],
            common_name=detection_species.split("_")[1],
            confidence=0.89,
        )

        await notification_manager._send_iot_notifications(detection)

        if mqtt_available and mock_mqtt is not None:
            mock_mqtt.publish_detection.assert_called_once_with(detection)
        if webhook_available and mock_webhook is not None:
            mock_webhook.send_detection_webhook.assert_called_once_with(detection)


class TestNotificationRules:
    """Test notification rule processing."""

    @pytest.mark.parametrize(
        "rule_config,detection_confidence,should_notify",
        [
            pytest.param(
                {
                    "name": "High Confidence",
                    "enabled": True,
                    "frequency": {"when": "immediate"},
                    "minimum_confidence": 90,
                    "service": "apprise",
                    "target": "test",
                    "scope": "all",
                },
                0.93,
                True,
                id="immediate-high-confidence",
            ),
            pytest.param(
                {
                    "name": "Disabled Rule",
                    "enabled": False,
                    "frequency": {"when": "immediate"},
                },
                0.87,
                False,
                id="disabled-rule",
            ),
            pytest.param(
                {
                    "name": "Daily Summary",
                    "enabled": True,
                    "frequency": {"when": "scheduled", "times": ["08:00", "20:00"]},
                },
                0.82,
                False,
                id="scheduled-not-immediate",
            ),
        ],
    )
    def test_notification_rules(
        self,
        test_config,
        notification_manager,
        caplog,
        model_factory,
        rule_config,
        detection_confidence,
        should_notify,
    ):
        """Should process notification rules correctly."""
        test_config.notification_rules = [rule_config]

        detection = model_factory.create_detection(
            species_tensor="Test species_Test Bird",
            scientific_name="Test species",
            common_name="Test Bird",
            confidence=detection_confidence,
        )

        with caplog.at_level(logging.INFO):
            notification_manager._handle_detection_event(None, detection)

        # Detection received should always be logged
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )
        # Note: Actual notification processing happens asynchronously

    def test_multiple_notification_rules(
        self, test_config, notification_manager, caplog, model_factory
    ):
        """Should process all matching immediate rules."""
        test_config.notification_rules = [
            {
                "name": "Rule 1",
                "enabled": True,
                "frequency": {"when": "immediate"},
                "service": "apprise",
                "target": "test",
                "scope": "all",
            },
            {
                "name": "Rule 2",
                "enabled": True,
                "frequency": {"when": "immediate"},
                "service": "apprise",
                "target": "test2",
                "scope": "all",
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

        # Detection received should be logged
        assert (
            f"NotificationManager received detection: {detection.get_display_name()}" in caplog.text
        )
        # Note: Actual rule processing happens asynchronously


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
        notification_manager.add_websocket(Mock(spec=WebSocket))

        with caplog.at_level(logging.DEBUG):
            # This runs in sync context (no event loop)
            notification_manager._handle_detection_event(None, detection)

        # Should log that async operations were skipped
        assert "No event loop running" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_detection_with_event_loop(self, notification_manager, model_factory):
        """Should handle detection events when event loop is running."""
        # Create mock websocket
        ws = Mock(spec=WebSocket)
        ws.send_text = AsyncMock(spec=callable)
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

    def test_register_listeners(
        self, mock_active_websockets, test_config, db_service_factory, mock_species_database, caplog
    ):
        """Should register detection signal listeners."""
        # Use the global db_service_factory pattern
        mock_core_database, _session, _result = db_service_factory()

        # Mock detection query service
        mock_detection_query_service = Mock(spec=DetectionQueryService)

        # Create new manager (without auto-registration)
        manager = NotificationManager(
            mock_active_websockets,
            test_config,
            mock_core_database,
            mock_species_database,
            mock_detection_query_service,
        )

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
    @pytest.mark.parametrize(
        "notification_type,health_data,method_name,mqtt_method,webhook_method",
        [
            pytest.param(
                "health",
                {"cpu_usage": 45.2, "memory_usage": 67.8, "disk_usage": 34.5, "temperature": 52.3},
                "send_system_health_notification",
                "publish_system_health",
                "send_health_webhook",
                id="system-health",
            ),
            pytest.param(
                "stats",
                {
                    "detection_count": 150,
                    "species_count": 25,
                    "uptime": 86400,
                    "last_detection": "2024-01-01T12:00:00",
                },
                "send_system_stats_notification",
                "publish_system_stats",
                "send_system_webhook",
                id="system-stats",
            ),
        ],
    )
    async def test_send_system_notifications(
        self,
        notification_manager,
        async_mock_factory,
        notification_type,
        health_data,
        method_name,
        mqtt_method,
        webhook_method,
    ):
        """Should send system notifications to all configured services."""
        # Setup mock services using factory
        mock_mqtt = async_mock_factory(MQTTService, **{mqtt_method: None})
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = async_mock_factory(WebhookService, **{webhook_method: None})
        notification_manager.webhook_service = mock_webhook

        # Call the appropriate method
        method = getattr(notification_manager, method_name)
        await method(health_data)

        # Verify both services were called
        getattr(mock_mqtt, mqtt_method).assert_called_once_with(health_data)
        getattr(mock_webhook, webhook_method).assert_called_once_with(health_data)

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
    @pytest.mark.parametrize(
        "method_name,data,error_message",
        [
            pytest.param(
                "send_system_health_notification",
                {"cpu_usage": 45.2},
                "Error sending system health IoT notifications",
                id="health-error",
            ),
            pytest.param(
                "send_system_stats_notification",
                {"uptime": 3600},
                "Error sending system stats IoT notifications",
                id="stats-error",
            ),
        ],
    )
    async def test_system_notification_errors(
        self, notification_manager, caplog, method_name, data, error_message
    ):
        """Should log error when system notifications fail."""
        mock_mqtt = Mock(spec=MQTTService)
        # Set up the mock method based on the notification type
        if "health" in method_name:
            mock_mqtt.publish_system_health = AsyncMock(
                spec=callable, side_effect=Exception("Connection failed")
            )
        else:
            mock_mqtt.publish_system_stats = AsyncMock(
                spec=callable, side_effect=Exception("Connection refused")
            )
        notification_manager.mqtt_service = mock_mqtt

        with caplog.at_level(logging.ERROR):
            method = getattr(notification_manager, method_name)
            await method(data)

        assert error_message in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "latitude,longitude,accuracy",
        [
            pytest.param(51.5074, -0.1278, 10.5, id="with-accuracy"),
            pytest.param(40.7128, -74.0060, None, id="without-accuracy"),
        ],
    )
    async def test_send_gps_notification(
        self, notification_manager, async_mock_factory, latitude, longitude, accuracy
    ):
        """Should send GPS notifications with correct parameters."""
        mock_mqtt = async_mock_factory(MQTTService, publish_gps_location=None)
        notification_manager.mqtt_service = mock_mqtt

        mock_webhook = async_mock_factory(WebhookService, send_gps_webhook=None)
        notification_manager.webhook_service = mock_webhook

        if accuracy is not None:
            await notification_manager.send_gps_notification(latitude, longitude, accuracy)
        else:
            await notification_manager.send_gps_notification(latitude, longitude)

        # Verify both services were called with correct parameters
        mock_mqtt.publish_gps_location.assert_called_once_with(latitude, longitude, accuracy)
        mock_webhook.send_gps_webhook.assert_called_once_with(latitude, longitude, accuracy)

    @pytest.mark.asyncio
    async def test_send_gps_notification_with_error(self, notification_manager, caplog):
        """Should log error when GPS notification fails."""
        mock_webhook = Mock(spec=WebhookService)
        mock_webhook.send_gps_webhook = AsyncMock(
            spec=callable, side_effect=Exception("Webhook timeout")
        )
        notification_manager.webhook_service = mock_webhook

        with caplog.at_level(logging.ERROR):
            await notification_manager.send_gps_notification(48.8566, 2.3522)

        assert "Error sending GPS IoT notifications" in caplog.text
        assert "Webhook timeout" in caplog.text


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
        mock_mqtt = Mock(spec=MQTTService)
        mock_mqtt.publish_detection = AsyncMock(
            spec=callable, side_effect=Exception("Network error")
        )
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
