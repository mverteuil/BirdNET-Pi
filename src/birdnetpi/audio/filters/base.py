"""Base audio filter class for the filtering framework."""

import logging
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class AudioFilter(ABC):
    """Abstract base class for audio filters.

    Audio filters process numpy arrays of int16 audio data in real-time.
    They are designed to be lightweight, efficient, and chainable.
    """

    def __init__(self, name: str, enabled: bool = True) -> None:
        """Initialize the audio filter.

        Args:
            name: Human-readable name for the filter
            enabled: Whether the filter is currently active
        """
        self.name = name
        self.enabled = enabled
        self._sample_rate: int | None = None
        self._channels: int | None = None
        logger.debug("AudioFilter '%s' initialized (enabled=%s)", name, enabled)

    def configure(self, sample_rate: int, channels: int) -> None:
        """Configure the filter for specific audio parameters.

        This method is called once when the filter is added to a pipeline
        to configure it for the specific audio stream characteristics.

        Args:
            sample_rate: Audio sample rate in Hz (e.g., 48000)
            channels: Number of audio channels (e.g., 1 for mono)
        """
        self._sample_rate = sample_rate
        self._channels = channels
        logger.debug(
            "AudioFilter '%s' configured: %dHz, %d channels", self.name, sample_rate, channels
        )

    @abstractmethod
    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Process a chunk of audio data.

        Args:
            audio_data: Input audio data as int16 numpy array
                       Shape: (samples,) for mono or (samples, channels) for multi-channel

        Returns:
            Processed audio data as int16 numpy array with same shape as input

        Raises:
            ValueError: If audio_data format is invalid
            RuntimeError: If filter is not properly configured
        """
        pass

    def apply(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply the filter to audio data if enabled.

        This is the main entry point for applying the filter. It handles
        enabled/disabled state and provides consistent error handling.

        Args:
            audio_data: Input audio data as int16 numpy array

        Returns:
            Processed audio data (or original data if filter is disabled)
        """
        if not self.enabled:
            return audio_data

        if self._sample_rate is None or self._channels is None:
            raise RuntimeError(f"Filter '{self.name}' not configured. Call configure() first.")

        if audio_data.dtype != np.int16:
            raise ValueError(f"Expected int16 audio data, got {audio_data.dtype}")

        try:
            return self.process(audio_data)
        except Exception as e:
            logger.error("Error in filter '%s': %s", self.name, e)
            # Return original data on error to maintain audio continuity
            return audio_data

    def enable(self) -> None:
        """Enable the filter."""
        self.enabled = True
        logger.debug("AudioFilter '%s' enabled", self.name)

    def disable(self) -> None:
        """Disable the filter."""
        self.enabled = False
        logger.debug("AudioFilter '%s' disabled", self.name)

    def get_parameters(self) -> dict[str, Any]:
        """Get current filter parameters.

        Returns:
            Dictionary of filter parameters for serialization/configuration
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "type": self.__class__.__name__,
            "sample_rate": self._sample_rate,
            "channels": self._channels,
        }

    def __str__(self) -> str:
        """Return string representation of the filter."""
        status = "enabled" if self.enabled else "disabled"
        return f"{self.__class__.__name__}('{self.name}', {status})"
