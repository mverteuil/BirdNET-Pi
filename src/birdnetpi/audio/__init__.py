"""Audio processing and management domain.

This module handles all audio-related functionality including:
- Audio capture and streaming
- Audio device management
- Audio file processing and storage
- Audio filtering and processing pipelines
- Spectrograms and visualizations
"""

from birdnetpi.audio.models import GUID, AudioFile, PathType
from birdnetpi.models.base import Base

__all__ = ["GUID", "AudioFile", "Base", "PathType"]
