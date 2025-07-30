from unittest.mock import MagicMock, patch

from birdnetpi.models.database_models import Detection
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.utils.signals import detection_signal


class TestDetectionEventPublisher:
    """Test the DetectionEventPublisher class."""

    def test_publish_detection(self):
        """Should create a Detection object and send it via signal."""
        publisher = DetectionEventPublisher()
        detection_data = {
            "common_name": "Common Blackbird",
            "scientific_name": "Turdus merula",
            "confidence": 0.95,
            "timestamp": "2025-07-29T10:00:00Z",
            "audio_file_id": 1,  # Assuming an ID for the foreign key
            "latitude": 0.0,
            "longitude": 0.0,
            "playback_url": "http://example.com/audio.wav",
            "filename": "audio.wav",
            "week": 30,
            "day": 29,
            "time": "10:00:00",
            "label": "common_blackbird",
            "auto_id": 123,
            "low_band_freq": 100,
            "high_band_freq": 1000,
        }

        with patch("birdnetpi.services.detection_event_publisher.Detection") as mock_detection:
            with patch.object(detection_signal, "send") as mock_send:
                mock_detection_instance = MagicMock(spec=Detection)
                mock_detection.return_value = mock_detection_instance

                publisher.publish_detection(detection_data)

                mock_detection.assert_called_once_with(**detection_data)
                mock_send.assert_called_once_with(publisher, detection=mock_detection_instance)
