import logging

import sounddevice as sd

from birdnetpi.models.audio_device import AudioDevice

logger = logging.getLogger(__name__)


class AudioDeviceService:
    """Service for discovering and managing audio devices."""

    def discover_input_devices(self) -> list[AudioDevice]:
        """Discovers available audio input devices and returns them as AudioDevice instances."""
        logger.info("Discovering audio input devices...")
        devices = sd.query_devices()
        input_devices: list[AudioDevice] = []

        for _, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                input_devices.append(
                    AudioDevice(
                        name=device["name"],
                        index=device["index"],
                        host_api_index=device["hostapi"],
                        max_input_channels=device["max_input_channels"],
                        max_output_channels=device["max_output_channels"],
                        default_low_input_latency=device["default_low_input_latency"],
                        default_low_output_latency=device["default_low_output_latency"],
                        default_high_input_latency=device["default_high_input_latency"],
                        default_high_output_latency=device["default_high_output_latency"],
                        default_samplerate=device["default_samplerate"],
                    )
                )
        logger.info(f"Found {len(input_devices)} input device(s).")
        return input_devices
