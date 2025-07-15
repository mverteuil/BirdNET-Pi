from unittest.mock import Mock

import pytest

from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.utils.signals import detection_event


@pytest.fixture
def publisher():
    """Provide a DetectionEventPublisher instance for testing."""
    return DetectionEventPublisher()


def test_publish_detection(publisher):
    """Should publish a detection event with the correct data"""
    mock_listener = Mock()
    detection_event.connect(mock_listener)

    test_data = {"species": "Test Bird", "confidence": 0.99}
    publisher.publish_detection(test_data)

    mock_listener.assert_called_once_with(publisher, data=test_data)

    detection_event.disconnect(mock_listener)
