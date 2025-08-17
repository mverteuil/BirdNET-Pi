import unittest
from multiprocessing import Queue
from unittest.mock import MagicMock, patch

from birdnetpi.config import BirdNETConfig
from birdnetpi.services.audio_capture_service import AudioCaptureService


class TestAudioCaptureService(unittest.TestCase):
    """Tests for the AudioCaptureService class."""

    def setUp(self):
        """Set up test environment before each test method."""
        self.mock_config = MagicMock(spec=BirdNETConfig)
        self.mock_config.audio_device_index = 1
        self.mock_config.sample_rate = 48000
        self.mock_config.audio_channels = 1
        self.mock_audio_queue = Queue()
        self.service = AudioCaptureService(
            self.mock_config, analysis_fifo_fd=-1, livestream_fifo_fd=-1
        )

    @patch("sounddevice.InputStream")
    def test_start_capture_initializes_stream(self, mock_input_stream):
        """Should initialize the sounddevice stream correctly."""
        self.service.start_capture()
        mock_input_stream.assert_called_once_with(
            device=self.mock_config.audio_device_index,
            samplerate=self.mock_config.sample_rate,
            channels=self.mock_config.audio_channels,
            callback=self.service._callback,
        )
        mock_input_stream.return_value.start.assert_called_once()

    @patch("sounddevice.InputStream")
    def test_stop_capture_stops__closes_stream(self, mock_input_stream):
        """Should stop and close the sounddevice stream."""
        mock_input_stream.return_value.stopped = False  # Ensure it's not stopped initially
        self.service.start_capture()
        self.service.stop_capture()
        mock_input_stream.return_value.stop.assert_called_once()
        mock_input_stream.return_value.close.assert_called_once()

    @patch("sounddevice.InputStream", side_effect=Exception("Test Error"))
    def test_start_capture_handles_exceptions(self, mock_input_stream):
        """Should handle exceptions during stream initialization."""
        mock_input_stream.side_effect = Exception("Test Error")
        with self.assertRaises(Exception) as cm:
            self.service.start_capture()
        self.assertEqual(str(cm.exception), "Test Error")
        # Verify error is logged
        with patch("birdnetpi.services.audio_capture_service.logger") as mock_logger:
            try:
                self.service.start_capture()
            except Exception:
                pass  # Expected exception
            mock_logger.error.assert_called_with(
                "Failed to start audio capture stream: %s", cm.exception
            )
