from dataclasses import dataclass


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
