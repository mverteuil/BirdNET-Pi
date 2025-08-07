import logging
from unittest.mock import Mock

import pytest

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.notification_service import NotificationService


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
def notification_service(mock_active_websockets, mock_config):
    """Provide a NotificationService instance for testing."""
    service = NotificationService(active_websockets=mock_active_websockets, config=mock_config)
    service.register_listeners()  # Listeners
    return service


def test_handle_detection_event_basic(notification_service, caplog):
    """Should log a basic notification message for detection event."""
    with caplog.at_level(logging.INFO):
        detection = Detection(
            species_tensor="Turdus merula_Common Blackbird",
            scientific_name="Turdus merula",
            common_name="Common Blackbird",
            confidence=0.95,
        )
        notification_service.active_websockets.add(Mock())  # Add a mock websocket
        notification_service._handle_detection_event(None, detection)
        assert (
            f"NotificationService received detection: {detection.get_display_name()}" in caplog.text
        )


def test_handle_detection_event_with_apprise_enabled(mock_config, notification_service, caplog):
    """Should log an Apprise notification message when enabled for detection event."""
    mock_config.apprise_notify_each_detection = True  # Correctly set the nested attribute
    with caplog.at_level(logging.INFO):
        detection = Detection(
            species_tensor="Erithacus rubecula_European Robin",
            scientific_name="Erithacus rubecula",
            common_name="European Robin",
            confidence=0.88,
        )
        notification_service.active_websockets.add(Mock())  # Add a mock websocket
        notification_service._handle_detection_event(None, detection)
        assert (
            f"NotificationService received detection: {detection.get_display_name()}" in caplog.text
        )
