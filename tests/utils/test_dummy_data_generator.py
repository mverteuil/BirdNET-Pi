import datetime
from unittest.mock import MagicMock

import pytest

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.utils.dummy_data_generator import generate_dummy_detections


@pytest.fixture
def mock_detection_manager():
    """Mock DetectionManager instance."""
    return MagicMock(spec=DetectionManager)


class TestDummyDataGenerator:
    """Test the TestDummyDataGenerator class."""

    def test_generate_dummy_detections(self, mock_detection_manager):
        """Generate the specified number of dummy detections and add them via DetectionManager."""
        num_detections = 5
        generate_dummy_detections(mock_detection_manager, num_detections)

        # Assert that create_detection was called the correct number of times
        assert mock_detection_manager.create_detection.call_count == num_detections

        # Assert that the data passed to create_detection is a DetectionEvent object
        for call_args in mock_detection_manager.create_detection.call_args_list:
            detection_event = call_args.args[0]
            assert isinstance(detection_event, DetectionEvent)
            assert isinstance(detection_event.timestamp, datetime.datetime)
            assert isinstance(detection_event.audio_file_path, str)
            assert isinstance(detection_event.duration, float)
            assert isinstance(detection_event.size_bytes, int)
            assert isinstance(detection_event.recording_start_time, datetime.datetime)
