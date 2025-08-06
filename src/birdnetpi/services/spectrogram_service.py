"""Real-time spectrogram generation service for audio visualization.

This service processes audio chunks to generate spectrogram data that can be
streamed to web clients for real-time visualization. It's designed to work
alongside the audio streaming pipeline with minimal performance impact.
"""

import asyncio
import logging
import time
from typing import Any

import numpy as np
from fastapi import WebSocket
from scipy import signal

logger = logging.getLogger(__name__)


class SpectrogramService:
    """Generates real-time spectrogram data from audio streams."""

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        window_size: int = 1024,
        overlap: float = 0.75,
        update_rate: float = 10.0,
    ) -> None:
        """Initialize the spectrogram service.

        Args:
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            window_size: FFT window size (power of 2 recommended)
            overlap: Window overlap fraction (0.0-1.0)
            update_rate: Spectrogram updates per second
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.window_size = window_size
        self.overlap = overlap
        self.update_rate = update_rate

        # Calculate derived parameters
        self.hop_length = int(window_size * (1 - overlap))
        self.samples_per_update = int(sample_rate / update_rate)

        # Audio buffer for accumulating samples
        self.audio_buffer = np.array([], dtype=np.int16)

        # WebSocket connections for spectrogram streaming
        self.connected_websockets = set[WebSocket]()

        # Frequency bins for display
        self.freq_bins = np.fft.fftfreq(window_size, 1 / sample_rate)[: window_size // 2]

        logger.info(
            "SpectrogramService initialized: %dHz, window=%d, hop=%d, update_rate=%.1fHz",
            sample_rate,
            window_size,
            self.hop_length,
            update_rate,
        )

    async def connect_websocket(self, websocket: WebSocket) -> None:
        """Register a WebSocket connection for spectrogram streaming."""
        self.connected_websockets.add(websocket)
        logger.info(
            "Spectrogram WebSocket connected. Total connections: %d", len(self.connected_websockets)
        )

        # Send initial configuration to new client
        config_data = {
            "type": "config",
            "sample_rate": self.sample_rate,
            "window_size": self.window_size,
            "freq_bins": self.freq_bins.tolist(),
            "update_rate": self.update_rate,
        }

        try:
            await websocket.send_json(config_data)
        except Exception as e:
            logger.error("Error sending config to new spectrogram client: %s", e)

    async def disconnect_websocket(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        self.connected_websockets.discard(websocket)
        logger.info(
            "Spectrogram WebSocket disconnected. Total connections: %d",
            len(self.connected_websockets),
        )

    async def process_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Process an audio chunk and generate spectrogram data if needed.

        Args:
            audio_data_bytes: Raw audio data as bytes (int16 format)
        """
        if not self.connected_websockets:
            return  # No clients to serve

        # Convert bytes to numpy array
        audio_samples = np.frombuffer(audio_data_bytes, dtype=np.int16)

        # Handle multi-channel audio by taking the first channel
        if self.channels > 1:
            audio_samples = audio_samples[:: self.channels]

        # Accumulate samples in buffer
        self.audio_buffer = np.append(self.audio_buffer, audio_samples)

        # Check if we have enough samples for an update
        if len(self.audio_buffer) >= self.samples_per_update:
            await self._generate_and_send_spectrogram()

            # Keep some overlap for continuity
            overlap_samples = int(self.samples_per_update * 0.25)
            self.audio_buffer = self.audio_buffer[-overlap_samples:]

    async def _generate_and_send_spectrogram(self) -> None:
        """Generate spectrogram from current buffer and send to clients."""
        try:
            # Use the most recent samples for spectrogram generation
            audio_segment = self.audio_buffer[-self.samples_per_update :]

            # Convert int16 to float for processing
            audio_float = audio_segment.astype(np.float32) / 32768.0

            # Generate spectrogram using Short-Time Fourier Transform
            _, _, spectrogram = signal.spectrogram(
                audio_float,
                fs=self.sample_rate,
                window="hann",
                nperseg=self.window_size,
                noverlap=int(self.window_size * self.overlap),
                mode="magnitude",
            )

            # Convert to dB scale for better visualization
            spectrogram_db = 20 * np.log10(np.maximum(spectrogram, 1e-10))

            # Prepare data for transmission
            spectrogram_data = {
                "type": "spectrogram",
                "timestamp": time.time(),  # Unix timestamp in seconds
                "data": spectrogram_db.tolist(),  # Convert numpy array to list for JSON
                "shape": spectrogram_db.shape,
            }

            # Send to all connected clients
            disconnected_clients = []
            for websocket in self.connected_websockets:
                try:
                    await websocket.send_json(spectrogram_data)
                except Exception as e:
                    logger.error("Error sending spectrogram data to client: %s", e)
                    disconnected_clients.append(websocket)

            # Remove disconnected clients
            for websocket in disconnected_clients:
                await self.disconnect_websocket(websocket)

        except Exception as e:
            logger.error("Error generating spectrogram: %s", e, exc_info=True)

    def get_parameters(self) -> dict[str, Any]:
        """Get current spectrogram parameters.

        Returns:
            Dictionary of current parameters
        """
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "window_size": self.window_size,
            "overlap": self.overlap,
            "update_rate": self.update_rate,
            "hop_length": self.hop_length,
            "freq_range": [0, self.sample_rate // 2],
            "connected_clients": len(self.connected_websockets),
        }
