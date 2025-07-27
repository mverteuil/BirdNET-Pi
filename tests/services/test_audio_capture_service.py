import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from multiprocessing import Queue

from birdnetpi.services.audio_capture_service import AudioCaptureService
from birdnetpi.models.birdnet_config import BirdNETConfig

class TestAudioCaptureService(unittest.TestCase):

    def setUp(self):
        self.mock_config = MagicMock(spec=BirdNETConfig)
        self.mock_config.audio_device_index = 1
        self.mock_config.sample_rate = 48000
        self.mock_config.audio_channels = 1
        self.mock_audio_queue = Queue()
        self.service = AudioCaptureService(self.mock_config, self.mock_audio_queue)

    @patch('sounddevice.InputStream')
    def test_start_capture_initializes_stream(self, MockInputStream):
        self.service.start_capture()
        MockInputStream.assert_called_once_with(
            device=self.mock_config.audio_device_index,
            samplerate=self.mock_config.sample_rate,
            channels=self.mock_config.audio_channels,
            callback=self.service._callback
        )
        self.service.stream.start.assert_called_once()

    @patch('sounddevice.InputStream')
    def test_stop_capture_stops_and_closes_stream(self, MockInputStream):
        self.service.start_capture()
        self.service.stop_capture()
        self.service.stream.stop.assert_called_once()
        self.service.stream.close.assert_called_once()

    @patch('sounddevice.InputStream')
    def test_callback_logs_audio_shape(self, MockInputStream):
        with patch('birdnetpi.services.audio_capture_service.logger') as mock_logger:
            indata = np.random.rand(1024, 1) # Simulate audio data
            self.service._callback(indata, 1024, None, None)
            mock_logger.info.assert_called_with(f"Audio data shape: {indata.shape}")

    @patch('sounddevice.InputStream', side_effect=Exception("Test Error"))
    def test_start_capture_handles_exceptions(self, MockInputStream):
        with self.assertRaises(Exception) as cm:
            self.service.start_capture()
        self.assertEqual(str(cm.exception), "Test Error")
        # Verify error is logged
        with patch('birdnetpi.services.audio_capture_service.logger') as mock_logger:
            try:
                self.service.start_capture()
            except Exception:
                pass # Expected exception
            mock_logger.error.assert_called_with(
                f"Failed to start audio capture stream: {cm.exception}"
            )
