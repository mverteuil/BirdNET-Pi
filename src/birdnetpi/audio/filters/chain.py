"""Filter chain for applying multiple audio filters in sequence."""

import logging

import numpy as np

from birdnetpi.audio.filters.base import AudioFilter

logger = logging.getLogger(__name__)


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
