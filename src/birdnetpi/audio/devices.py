import logging
from dataclasses import asdict, dataclass

import sounddevice as sd

from birdnetpi.utils.cache import cached

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents an audio input/output device."""

    name: str
    index: int
    host_api_index: int
    max_input_channels: int
    max_output_channels: int
    default_low_input_latency: float
    default_low_output_latency: float
    default_high_input_latency: float
    default_high_output_latency: float
    default_samplerate: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


class AudioDeviceService:
    """Service for discovering and managing audio devices."""

    @cached(ttl=60, key_prefix="audio_devices")  # Cache for 60 seconds
    def discover_input_devices(self) -> list[AudioDevice]:
        """Discovers available audio input devices and returns them as AudioDevice instances."""
        logger.debug("Discovering audio input devices...")

        # Force sounddevice to re-query devices instead of using cached results
        # This is important when PulseAudio connection might not be ready at import time
        try:
            # Reset the internal state to force a fresh query
            sd._terminate()
            sd._initialize()
        except Exception:
            # If reset fails, continue with normal query
            pass

        devices = sd.query_devices()
        input_devices: list[AudioDevice] = []

        for _, device in enumerate(devices):
            if device["max_input_channels"] > 0:  # type: ignore[index,misc]
                input_devices.append(
                    AudioDevice(  # type: ignore[misc]
                        name=device["name"],  # type: ignore[index]
                        index=device["index"],  # type: ignore[index]
                        host_api_index=device["hostapi"],  # type: ignore[index]
                        max_input_channels=device["max_input_channels"],  # type: ignore[index]
                        max_output_channels=device["max_output_channels"],  # type: ignore[index]
                        default_low_input_latency=device["default_low_input_latency"],  # type: ignore[index]
                        default_low_output_latency=device["default_low_output_latency"],  # type: ignore[index]
                        default_high_input_latency=device["default_high_input_latency"],  # type: ignore[index]
                        default_high_output_latency=device["default_high_output_latency"],  # type: ignore[index]
                        default_samplerate=device["default_samplerate"],  # type: ignore[index]
                    )
                )
        logger.debug(f"Found {len(input_devices)} input device(s).")
        return input_devices
