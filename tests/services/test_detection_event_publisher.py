from unittest.mock import Mock, patch

import pytest

from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.utils.signals import detection_signal


@pytest.fixture
def publisher():
    """Provide a DetectionEventPublisher instance for testing."""
    return DetectionEventPublisher()


def test_publish_detection(publisher):
    """Should publish a detection event with the correct data"""
    mock_listener = Mock()
    detection_signal.connect(mock_listener)

    test_data = {"species": "Test Bird", "confidence": 0.99}
    with patch("birdnetpi.services.detection_event_publisher.Detection") as mock_detection_class:
        mock_detection_instance = mock_detection_class.return_value
        publisher.publish_detection(test_data)
        mock_listener.assert_called_once_with(publisher, detection=mock_detection_instance)

    detection_signal.disconnect(mock_listener)
