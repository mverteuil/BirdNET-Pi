import shutil
from pathlib import Path

import soundfile as sf

from birdnetpi.detections.models import AudioFile
from birdnetpi.system.path_resolver import PathResolver


class FileManager:
    """Manages file system operations using PathResolver."""

    def __init__(self, path_resolver: PathResolver) -> None:
        self.path_resolver = path_resolver
        self.base_path = path_resolver.data_dir

    def create_directory(self, relative_path: Path, exist_ok: bool = True) -> None:
        """Create a directory within the base_path."""
        full_path = self.base_path / relative_path
        full_path.mkdir(parents=True, exist_ok=exist_ok)

    def delete_file(self, relative_path: Path) -> None:
        """Delete a file within the base_path."""
        full_path = self.base_path / relative_path
        if full_path.is_file():
            full_path.unlink()

    def delete_directory(self, relative_path: Path) -> None:
        """Delete a directory and its contents within the base_path."""
        full_path = self.base_path / relative_path
        if full_path.is_dir():
            shutil.rmtree(full_path)

    def list_directory_contents(self, relative_path: Path) -> list[str]:
        """List the contents of a directory within the base_path."""
        full_path = self.base_path / relative_path
        return [str(p.name) for p in full_path.iterdir()] if full_path.is_dir() else []

    def file_exists(self, relative_path: Path) -> bool:
        """Check if a file exists within the base_path."""
        full_path = self.base_path / relative_path
        return full_path.is_file()

    def directory_exists(self, relative_path: Path) -> bool:
        """Check if a directory exists within the base_path."""
        full_path = self.base_path / relative_path
        return full_path.is_dir()

    def read_file(self, relative_path: Path, encoding: str = "utf-8") -> str:
        """Read content from a file within the base_path."""
        full_path = self.base_path / relative_path
        return full_path.read_text(encoding=encoding)

    def write_file(self, relative_path: Path, content: str, encoding: str = "utf-8") -> None:
        """Write content to a file within the base_path."""
        full_path = self.base_path / relative_path
        full_path.write_text(content, encoding=encoding)

    def save_detection_audio(
        self,
        relative_path: Path,
        raw_audio_bytes: bytes,
        sample_rate: int,
        channels: int,
    ) -> AudioFile:
        """Save raw audio bytes to a WAV file and return an in-memory AudioFile instance.

        Args:
            relative_path: Path relative to recordings directory
            raw_audio_bytes: Raw audio data as bytes
            sample_rate: Sample rate in Hz
            channels: Number of audio channels

        Returns:
            AudioFile instance with path relative to recordings directory
        """
        import numpy as np

        # The relative_path is now relative to recordings dir, not data dir
        recordings_dir = self.path_resolver.get_recordings_dir()
        full_path = recordings_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert bytes to numpy array
        audio_array = np.frombuffer(raw_audio_bytes, dtype=np.int16)

        # Reshape for the correct number of channels
        if channels > 1:
            # Reshape to (samples, channels) for multi-channel audio
            audio_array = audio_array.reshape(-1, channels)

        # Write the audio file
        sf.write(str(full_path), audio_array, sample_rate, subtype="PCM_16")

        duration = len(raw_audio_bytes) / (
            sample_rate * channels * 2
        )  # 2 bytes per sample for int16
        size_bytes = len(raw_audio_bytes)

        return AudioFile(
            file_path=relative_path,
            duration=duration,
            size_bytes=size_bytes,
        )
