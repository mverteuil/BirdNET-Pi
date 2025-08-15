"""BirdNET-Pi daemon processes.

This package contains long-running daemon processes that handle various
background tasks for the BirdNET-Pi system:

- audio_analysis_daemon: Analyzes audio files for bird detections
- audio_capture_daemon: Captures audio from input devices
- audio_websocket_daemon: Streams audio over WebSocket connections
- spectrogram_websocket_daemon: Generates and streams spectrograms over WebSocket
"""

__all__ = [
    "audio_analysis_daemon",
    "audio_capture_daemon",
    "audio_websocket_daemon",
    "spectrogram_websocket_daemon",
]
