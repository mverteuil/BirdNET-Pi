"""Audio resampling filter for sample rate conversion."""

import logging
from typing import Any

import librosa
import numpy as np

from birdnetpi.audio.filters.base import AudioFilter

logger = logging.getLogger(__name__)


class ResampleFilter(AudioFilter):
    """Resample audio from one sample rate to another.

    This filter is essential when the audio capture device's native sample rate
    differs from what the BirdNET model expects (48kHz). It uses high-quality
    resampling to preserve audio fidelity during rate conversion.
    """

    def __init__(
        self,
        target_sample_rate: int,
        name: str = "Resample",
        enabled: bool = True,
    ) -> None:
        """Initialize the resample filter.

        Args:
            target_sample_rate: Target sample rate in Hz (e.g., 48000 for BirdNET)
            name: Human-readable name for the filter
            enabled: Whether the filter is currently active
        """
        super().__init__(name, enabled)
        self.target_sample_rate = target_sample_rate
        self.source_sample_rate: int | None = None

    def configure(self, sample_rate: int, channels: int) -> None:
        """Configure the filter for specific audio parameters.

        This is called once when the filter is added to the chain.
        """
        super().configure(sample_rate, channels)
        self.source_sample_rate = sample_rate

        if sample_rate == self.target_sample_rate:
            logger.info(
                "ResampleFilter '%s': rates match %dHz, will pass through",
                self.name,
                sample_rate,
            )
        else:
            logger.info(
                "ResampleFilter '%s' configured: %dHz -> %dHz",
                self.name,
                sample_rate,
                self.target_sample_rate,
            )

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Resample audio data to the target sample rate.

        Args:
            audio_data: Input audio data as int16 numpy array

        Returns:
            Resampled audio data as int16 numpy array
        """
        if self.source_sample_rate is None:
            raise RuntimeError(f"ResampleFilter '{self.name}' not configured")

        # If rates match, no resampling needed
        if self.source_sample_rate == self.target_sample_rate:
            return audio_data

        # Convert int16 to float for processing
        audio_float = audio_data.astype(np.float32) / 32768.0

        # Resample using librosa's high-quality resampler
        resampled_float = librosa.resample(
            audio_float,
            orig_sr=self.source_sample_rate,
            target_sr=self.target_sample_rate,
            res_type="kaiser_best",  # High quality resampling
        )

        # Convert back to int16, with clipping to prevent overflow
        resampled_int16 = np.clip(resampled_float * 32768.0, -32768, 32767).astype(np.int16)

        logger.debug(
            "Resampled audio from %d to %d samples (%dHz -> %dHz)",
            len(audio_data),
            len(resampled_int16),
            self.source_sample_rate,
            self.target_sample_rate,
        )

        return resampled_int16

    def get_parameters(self) -> dict[str, Any]:
        """Get current filter parameters."""
        params = super().get_parameters()
        params.update(
            {
                "target_sample_rate": self.target_sample_rate,
                "source_sample_rate": self.source_sample_rate,
            }
        )
        return params
