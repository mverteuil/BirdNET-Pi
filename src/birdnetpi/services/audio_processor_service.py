import logging

import librosa
import numpy as np

log = logging.getLogger(__name__)


class AudioProcessorService:
    """Handles low-level audio file reading and processing (e.g., chunking)."""

    def __init__(self) -> None:
        pass

    def _split_signal(
        self,
        sig: np.ndarray,
        rate: int,
        overlap: float,
        seconds: float = 3.0,
        minlen: float = 1.5,
    ) -> list[np.ndarray]:
        """Split a continuous audio signal into fixed-length chunks with overlap."""
        sig_splits = []
        for i in range(0, len(sig), int((seconds - overlap) * rate)):
            split = sig[i : i + int(seconds * rate)]

            # End of signal? Break if chunk is too short after minimum length
            if len(split) < int(minlen * rate):
                break

            # Signal chunk too short? Fill with zeros to match expected length
            if len(split) < int(rate * seconds):
                temp = np.zeros(int(rate * seconds))
                temp[: len(split)] = split
                split = temp

            sig_splits.append(split)

        return sig_splits

    def read_audio_data(
        self, path: str, overlap: float, sample_rate: int = 48000
    ) -> list[np.ndarray]:
        """Read an audio file and return it as a list of processed NumPy array chunks."""
        log.info("AudioProcessorService: READING AUDIO DATA...")
        try:
            # Open file with librosa (uses ffmpeg or libav)
            sig, rate = librosa.load(path, sr=sample_rate, mono=True, res_type="kaiser_fast")

            # Split audio into 3-second chunks (default for BirdNET)
            chunks = self._split_signal(sig, rate, overlap)

            log.info("AudioProcessorService: READING DONE! READ %d CHUNKS.", len(chunks))
            return chunks
        except Exception as e:
            log.error(f"AudioProcessorService: Error reading audio file {path}: {e}")
            raise  # Re-raise the exception after logging
