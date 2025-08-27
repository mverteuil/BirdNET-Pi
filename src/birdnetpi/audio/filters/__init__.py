"""Audio filtering framework for real-time audio processing.

This package provides filters for processing audio streams in the BirdNET-Pi system.
Filters can be chained together to create complex processing pipelines.
"""

from birdnetpi.audio.filters.base import AudioFilter
from birdnetpi.audio.filters.chain import FilterChain
from birdnetpi.audio.filters.frequency import HighPassFilter, LowPassFilter
from birdnetpi.audio.filters.passthrough import PassThroughFilter
from birdnetpi.audio.filters.resample import ResampleFilter

__all__ = [
    "AudioFilter",
    "FilterChain",
    "HighPassFilter",
    "LowPassFilter",
    "PassThroughFilter",
    "ResampleFilter",
]
