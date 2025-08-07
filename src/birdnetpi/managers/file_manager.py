import shutil
from datetime import datetime
from pathlib import Path

import soundfile as sf

from birdnetpi.models.database_models import AudioFile


class FileManager:
    """Manages file system operations within a specified base path."""

    def __init__(self, base_path: str) -> None:
        self.base_path = Path(base_path)

    def get_full_path(self, relative_path: str) -> Path:
        """Return the full absolute Path for a given relative path within the base_path."""
        return self.base_path / relative_path

    def get_absolute_path(self, relative_path: str) -> Path:
        """Return the absolute Path for a given relative path within the base_path."""
        return self.get_full_path(relative_path).resolve()

    def create_directory(self, relative_path: str, exist_ok: bool = True) -> None:
        """Create a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        full_path.mkdir(parents=True, exist_ok=exist_ok)

    def delete_file(self, relative_path: str) -> None:
        """Delete a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_file():
            full_path.unlink()

    def delete_directory(self, relative_path: str) -> None:
        """Delete a directory and its contents within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_dir():
            shutil.rmtree(full_path)

    def list_directory_contents(self, relative_path: str) -> list[str]:
        """List the contents of a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_dir():
            return [str(p.name) for p in full_path.iterdir()]
        return []

    def file_exists(self, relative_path: str) -> bool:
        """Check if a file exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.is_file()

    def directory_exists(self, relative_path: str) -> bool:
        """Check if a directory exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.is_dir()

    def read_file(self, relative_path: str, mode: str = "r", encoding: str = "utf-8") -> str:
        """Read content from a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.read_text(encoding=encoding)

    def write_file(
        self, relative_path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> None:
        """Write content to a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        full_path.write_text(content, encoding=encoding)

    def save_detection_audio(
        self,
        relative_path: str,
        raw_audio_bytes: bytes,
        sample_rate: int,
        channels: int,
    ) -> AudioFile:
        """Save raw audio bytes to a WAV file and return an in-memory AudioFile instance."""
        full_path = self.get_full_path(relative_path)
        self.create_directory(str(full_path.parent), exist_ok=True)

        # Assuming raw_audio_bytes is int16 data
        sf.write(full_path, raw_audio_bytes, sample_rate, subtype="PCM_16")

        duration = len(raw_audio_bytes) / (
            sample_rate * channels * 2
        )  # 2 bytes per sample for int16
        size_bytes = len(raw_audio_bytes)

        return AudioFile(
            file_path=relative_path,
            duration=duration,
            size_bytes=size_bytes,
        )
