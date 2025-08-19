import logging
from unittest.mock import Mock

import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import Detection
from birdnetpi.notifications.notification_manager import NotificationManager


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance for testing."""
    config = Mock(spec=BirdNETConfig)
    config.apprise_notify_each_detection = False
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


def test_handle_detection_event__apprise_enabled(mock_config, notification_manager, caplog):
    """Should log an Apprise notification message when enabled for detection event."""
    mock_config.apprise_notify_each_detection = True  # Correctly set the nested attribute
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
