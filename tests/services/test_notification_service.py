from unittest.mock import Mock

import pytest

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.notification_service import NotificationService


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance for testing."""
    config = Mock(spec=BirdNETConfig)
    config.apprise_notify_each_detection = False
    return config


@pytest.fixture
def notification_service(mock_config):
    """Provide a NotificationService instance for testing."""
    return NotificationService(config=mock_config)


def test_species_notifier_basic(notification_service, capsys):
    """Should print a basic notification message"""
    detection = Detection(species="Common Blackbird", confidence=0.95)
    notification_service.species_notifier(detection)
    captured = capsys.readouterr()
    assert (
        "Notification: New species detected - "
        f"{detection.species} with confidence {detection.confidence:.2f}" in captured.out
    )


def test_species_notifier_with_apprise_enabled(mock_config, notification_service, capsys):
    """Should print an Apprise notification message when enabled"""
    mock_config.apprise_notify_each_detection = True
    detection = Detection(species="European Robin", confidence=0.88)
    notification_service.species_notifier(detection)
    captured = capsys.readouterr()
    assert (
        "Notification: New species detected - "
        f"{detection.species} with confidence {detection.confidence:.2f}" in captured.out
    )
    assert f"Sending Apprise notification for {detection.species}" in captured.out
