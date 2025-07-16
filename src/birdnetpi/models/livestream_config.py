from dataclasses import dataclass


@dataclass
class LivestreamConfig:
    """Configuration for audio livestreaming."""

    input_device: str
    output_url: str
