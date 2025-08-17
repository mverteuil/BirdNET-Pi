from unittest.mock import patch

import pytest

from birdnetpi.audio.audio_device_service import AudioDevice, AudioDeviceService


class TestAudioDeviceService:
    """Should test the AudioDeviceService class."""

    @pytest.fixture(autouse=True)
    def audio_device_service(self):
        """Set up test fixtures."""
        self.service = AudioDeviceService()

    @patch("sounddevice.query_devices")
    def test_discover_input_devices(self, mock_query_devices):
        """Should correctly identify and return input devices."""
        # Mock sounddevice.query_devices to return a list of dummy devices
        mock_query_devices.return_value = [
            {
                "name": "Device 1",
                "index": 0,
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_low_input_latency": 0.01,
                "default_low_output_latency": 0.0,
                "default_high_input_latency": 0.05,
                "default_high_output_latency": 0.0,
                "default_samplerate": 44100.0,
            },
            {
                "name": "Device 2 (Output Only)",
                "index": 1,
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_low_input_latency": 0.0,
                "default_low_output_latency": 0.01,
                "default_high_input_latency": 0.0,
                "default_high_output_latency": 0.05,
                "default_samplerate": 44100.0,
            },
            {
                "name": "Device 3",
                "index": 2,
                "hostapi": 0,
                "max_input_channels": 1,
                "max_output_channels": 1,
                "default_low_input_latency": 0.01,
                "default_low_output_latency": 0.01,
                "default_high_input_latency": 0.05,
                "default_high_output_latency": 0.05,
                "default_samplerate": 48000.0,
            },
        ]

        devices = self.service.discover_input_devices()

        # Assert that query_devices was called
        mock_query_devices.assert_called_once()

        # Assert that only input devices are returned
        assert len(devices) == 2

        # Assert that the returned objects are AudioDevice instances
        assert isinstance(devices[0], AudioDevice)
        assert isinstance(devices[1], AudioDevice)

        # Assert the data is correctly mapped for the first device
        assert devices[0].name == "Device 1"
        assert devices[0].index == 0
        assert devices[0].host_api_index == 0
        assert devices[0].max_input_channels == 2
        assert devices[0].max_output_channels == 0
        assert devices[0].default_low_input_latency == 0.01
        assert devices[0].default_low_output_latency == 0.0
        assert devices[0].default_high_input_latency == 0.05
        assert devices[0].default_high_output_latency == 0.0
        assert devices[0].default_samplerate == 44100.0

        # Assert the data is correctly mapped for the second device
        assert devices[1].name == "Device 3"
        assert devices[1].index == 2
        assert devices[1].host_api_index == 0
        assert devices[1].max_input_channels == 1
        assert devices[1].max_output_channels == 1
        assert devices[1].default_low_input_latency == 0.01
        assert devices[1].default_low_output_latency == 0.01
        assert devices[1].default_high_input_latency == 0.05
        assert devices[1].default_high_output_latency == 0.05
        assert devices[1].default_samplerate == 48000.0
