"""Pass-through filter for testing and as a base for other filters."""

import numpy as np

from birdnetpi.audio.filters.base import AudioFilter


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
