import unittest
from multiprocessing import Queue
from unittest.mock import MagicMock, patch

from birdnetpi.audio.capture import AudioCaptureService
from birdnetpi.config import BirdNETConfig


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

    @patch("sounddevice.query_devices")
    @patch("sounddevice.InputStream")
    def test_start_capture_initializes_stream(self, mock_input_stream, mock_query_devices):
        """Should initialize the sounddevice stream correctly."""
        # Mock the device to return its default sample rate
        mock_device_info = {"default_samplerate": 44100.0}
        mock_query_devices.return_value = mock_device_info

        # Mock the audio device service
        mock_device = MagicMock()
        mock_device.index = 1
        mock_device.default_samplerate = 44100.0
        mock_device.name = "Test Device"
        self.service.audio_device_service.discover_input_devices = MagicMock(
            return_value=[mock_device]
        )

        self.service.start_capture()

        # Should use device's native sample rate (44100) not config sample rate (48000)
        mock_input_stream.assert_called_once_with(
            device=self.mock_config.audio_device_index,
            samplerate=44100,  # Device's native rate
            channels=self.mock_config.audio_channels,
            callback=self.service._callback,
        )
        mock_input_stream.return_value.start.assert_called_once()

    @patch("sounddevice.query_devices")
    @patch("sounddevice.InputStream")
    def test_stop_capture_stops__closes_stream(self, mock_input_stream, mock_query_devices):
        """Should stop and close the sounddevice stream."""
        # Mock the device
        mock_device_info = {"default_samplerate": 48000.0}
        mock_query_devices.return_value = mock_device_info
        mock_device = MagicMock()
        mock_device.index = 1
        mock_device.default_samplerate = 48000.0
        mock_device.name = "Test Device"
        self.service.audio_device_service.discover_input_devices = MagicMock(
            return_value=[mock_device]
        )

        mock_input_stream.return_value.stopped = False  # Ensure it's not stopped initially
        self.service.start_capture()
        self.service.stop_capture()
        # Now using abort() for immediate stop instead of stop()
        mock_input_stream.return_value.abort.assert_called_once()
        mock_input_stream.return_value.close.assert_called_once()

    @patch("sounddevice.query_devices")
    @patch("sounddevice.InputStream", side_effect=Exception("Test Error"))
    def test_start_capture_handles_exceptions(self, mock_input_stream, mock_query_devices):
        """Should handle exceptions during stream initialization."""
        # Mock the device
        mock_device_info = {"default_samplerate": 48000.0}
        mock_query_devices.return_value = mock_device_info
        mock_device = MagicMock()
        mock_device.index = 1
        mock_device.default_samplerate = 48000.0
        mock_device.name = "Test Device"
        self.service.audio_device_service.discover_input_devices = MagicMock(
            return_value=[mock_device]
        )

        mock_input_stream.side_effect = Exception("Test Error")
        with self.assertRaises(Exception) as cm:
            self.service.start_capture()
        self.assertEqual(str(cm.exception), "Test Error")
        # Verify error is logged
        with patch("birdnetpi.audio.capture.logger") as mock_logger:
            try:
                self.service.start_capture()
            except Exception:
                pass  # Expected exception
            mock_logger.error.assert_called_with(
                "Failed to start audio capture stream: %s", cm.exception
            )
