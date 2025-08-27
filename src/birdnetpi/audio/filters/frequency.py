"""Frequency-based audio filters for noise reduction."""

import logging
from typing import Any

import numpy as np
from scipy import signal

from birdnetpi.audio.filters.base import AudioFilter

logger = logging.getLogger(__name__)


class HighPassFilter(AudioFilter):
    """High-pass filter for removing low-frequency noise.

    Useful for reducing traffic noise, HVAC hum, and other low-frequency
    environmental sounds that can mask bird calls.
    """

    def __init__(
        self,
        cutoff_frequency: float,
        name: str = "HighPass",
        enabled: bool = True,
        order: int = 4,
    ) -> None:
        """Initialize the high-pass filter.

        Args:
            cutoff_frequency: Cutoff frequency in Hz (frequencies below this are attenuated)
            name: Human-readable name for the filter
            enabled: Whether the filter is currently active
            order: Filter order (higher = steeper rolloff, more processing)
        """
        super().__init__(name, enabled)
        self.cutoff_frequency = cutoff_frequency
        self.order = order
        self._sos = None  # Second-order sections for filtering

    def configure(self, sample_rate: int, channels: int) -> None:
        """Configure the filter for specific audio parameters."""
        super().configure(sample_rate, channels)

        # Calculate normalized cutoff frequency (0-1 range)
        nyquist = sample_rate / 2
        normalized_cutoff = self.cutoff_frequency / nyquist

        if normalized_cutoff >= 1.0:
            logger.warning(
                "HighPassFilter '%s': cutoff %dHz >= Nyquist %dHz, filter will have no effect",
                self.name,
                self.cutoff_frequency,
                nyquist,
            )
            normalized_cutoff = 0.99  # Clamp to valid range

        # Create second-order sections for stable filtering
        self._sos = signal.butter(self.order, normalized_cutoff, btype="high", output="sos")
        logger.debug(
            "HighPassFilter '%s' configured: %dHz cutoff, order %d",
            self.name,
            self.cutoff_frequency,
            self.order,
        )

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply high-pass filtering to audio data.

        Args:
            audio_data: Input audio data as int16 numpy array

        Returns:
            Filtered audio data as int16 numpy array
        """
        if self._sos is None:
            raise RuntimeError(f"HighPassFilter '{self.name}' not configured")

        # Convert int16 to float for processing (preserves precision)
        audio_float = audio_data.astype(np.float32) / 32768.0

        # Apply filter using second-order sections
        filtered_float = signal.sosfilt(self._sos, audio_float, axis=0)

        # Convert back to int16, with clipping to prevent overflow
        filtered_int16 = np.clip(filtered_float * 32768.0, -32768, 32767).astype(np.int16)

        return filtered_int16

    def get_parameters(self) -> dict[str, Any]:
        """Get current filter parameters."""
        params = super().get_parameters()
        params.update(
            {
                "cutoff_frequency": self.cutoff_frequency,
                "order": self.order,
            }
        )
        return params


class LowPassFilter(AudioFilter):
    """Low-pass filter for removing high-frequency noise.

    Useful for reducing harsh sounds like children's voices, sirens,
    and other high-frequency environmental noise that can be unpleasant
    for human listening while preserving bird calls.
    """

    def __init__(
        self,
        cutoff_frequency: float,
        name: str = "LowPass",
        enabled: bool = True,
        order: int = 4,
    ) -> None:
        """Initialize the low-pass filter.

        Args:
            cutoff_frequency: Cutoff frequency in Hz (frequencies above this are attenuated)
            name: Human-readable name for the filter
            enabled: Whether the filter is currently active
            order: Filter order (higher = steeper rolloff, more processing)
        """
        super().__init__(name, enabled)
        self.cutoff_frequency = cutoff_frequency
        self.order = order
        self._sos = None  # Second-order sections for filtering

    def configure(self, sample_rate: int, channels: int) -> None:
        """Configure the filter for specific audio parameters."""
        super().configure(sample_rate, channels)

        # Calculate normalized cutoff frequency (0-1 range)
        nyquist = sample_rate / 2
        normalized_cutoff = self.cutoff_frequency / nyquist

        if normalized_cutoff >= 1.0:
            logger.warning(
                "LowPassFilter '%s': cutoff %dHz >= Nyquist %dHz, using maximum cutoff",
                self.name,
                self.cutoff_frequency,
                nyquist,
            )
            normalized_cutoff = 0.99  # Clamp to valid range

        # Create second-order sections for stable filtering
        self._sos = signal.butter(self.order, normalized_cutoff, btype="low", output="sos")
        logger.debug(
            "LowPassFilter '%s' configured: %dHz cutoff, order %d",
            self.name,
            self.cutoff_frequency,
            self.order,
        )

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply low-pass filtering to audio data.

        Args:
            audio_data: Input audio data as int16 numpy array

        Returns:
            Filtered audio data as int16 numpy array
        """
        if self._sos is None:
            raise RuntimeError(f"LowPassFilter '{self.name}' not configured")

        # Convert int16 to float for processing (preserves precision)
        audio_float = audio_data.astype(np.float32) / 32768.0

        # Apply filter using second-order sections
        filtered_float = signal.sosfilt(self._sos, audio_float, axis=0)

        # Convert back to int16, with clipping to prevent overflow
        filtered_int16 = np.clip(filtered_float * 32768.0, -32768, 32767).astype(np.int16)

        return filtered_int16

    def get_parameters(self) -> dict[str, Any]:
        """Get current filter parameters."""
        params = super().get_parameters()
        params.update(
            {
                "cutoff_frequency": self.cutoff_frequency,
                "order": self.order,
            }
        )
        return params
