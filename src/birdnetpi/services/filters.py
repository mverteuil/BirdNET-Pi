"""Audio filtering framework for real-time audio processing.

This module provides the base framework for implementing audio filters that can be
applied to live audio streams in the BirdNET-Pi system. Filters are designed to
work with numpy arrays of int16 audio data and support chaining for complex
processing pipelines.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from scipy import signal

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


class PassThroughFilter(AudioFilter):
    """A pass-through filter that does not modify audio data.

    Useful for testing the filter framework and as a base for other filters.
    """

    def __init__(self, name: str = "PassThrough", enabled: bool = True) -> None:
        """Initialize the pass-through filter."""
        super().__init__(name, enabled)

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Return audio data unchanged.

        Args:
            audio_data: Input audio data

        Returns:
            Same audio data without modification
        """
        return audio_data


class FilterChain:
    """Container for multiple audio filters applied in sequence.

    The FilterChain applies filters in order, passing the output of each
    filter as input to the next filter in the chain.
    """

    def __init__(self, name: str = "FilterChain") -> None:
        """Initialize an empty filter chain.

        Args:
            name: Name for this filter chain
        """
        self.name = name
        self.filters: list[AudioFilter] = []
        self._configured = False
        logger.debug("FilterChain '%s' initialized", name)

    def add_filter(self, filter_instance: AudioFilter) -> None:
        """Add a filter to the end of the chain.

        Args:
            filter_instance: AudioFilter instance to add
        """
        self.filters.append(filter_instance)
        # If chain is already configured, configure the new filter
        if self._configured and hasattr(self, "_sample_rate"):
            filter_instance.configure(self._sample_rate, self._channels)
        logger.debug("Added filter '%s' to chain '%s'", filter_instance.name, self.name)

    def remove_filter(self, filter_name: str) -> bool:
        """Remove a filter from the chain by name.

        Args:
            filter_name: Name of the filter to remove

        Returns:
            True if filter was found and removed, False otherwise
        """
        for i, filter_instance in enumerate(self.filters):
            if filter_instance.name == filter_name:
                self.filters.pop(i)
                logger.debug("Removed filter '%s' from chain '%s'", filter_name, self.name)
                return True
        logger.warning("Filter '%s' not found in chain '%s'", filter_name, self.name)
        return False

    def configure(self, sample_rate: int, channels: int) -> None:
        """Configure all filters in the chain.

        Args:
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
        """
        self._sample_rate = sample_rate
        self._channels = channels
        self._configured = True

        for filter_instance in self.filters:
            filter_instance.configure(sample_rate, channels)

        logger.debug(
            "FilterChain '%s' configured: %dHz, %d channels", self.name, sample_rate, channels
        )

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Process audio data through all filters in the chain.

        Args:
            audio_data: Input audio data as int16 numpy array

        Returns:
            Audio data after processing through all enabled filters
        """
        result = audio_data
        for filter_instance in self.filters:
            result = filter_instance.apply(result)
        return result

    def clear(self) -> None:
        """Remove all filters from the chain."""
        filter_count = len(self.filters)
        self.filters.clear()
        logger.debug("Cleared %d filters from chain '%s'", filter_count, self.name)

    def get_filter_names(self) -> list[str]:
        """Get list of filter names in the chain.

        Returns:
            List of filter names in order
        """
        return [f.name for f in self.filters]

    def __len__(self) -> int:
        """Return number of filters in the chain."""
        return len(self.filters)

    def __str__(self) -> str:
        """Return string representation of the filter chain."""
        enabled_count = sum(1 for f in self.filters if f.enabled)
        return f"FilterChain('{self.name}', {enabled_count}/{len(self.filters)} filters enabled)"


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
