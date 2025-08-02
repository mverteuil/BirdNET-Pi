import os
from datetime import datetime


class FilePathResolver:
    """Resolves absolute file paths within the BirdNET-Pi project structure."""

    def __init__(self) -> None:
        # Determine the repository root dynamically
        # This file is in BirdNET-Pi/src/birdnetpi/utils/
        # So, go up three directories to reach BirdNET-Pi/
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    def resolve(self, *paths: str) -> str:
        """Resolve an absolute path from the base directory and given subpaths."""
        return os.path.join(self.base_dir, *paths)

    def get_birds_db_path(self) -> str:
        """Return the absolute path to the birds.db file."""
        return self.resolve("scripts", "birds.db")

    def get_extracted_birdsounds_path(self) -> str:
        """Return the absolute path to the extracted birdsounds directory."""
        return self.resolve("BirdSongs", "Extracted", "By_Date")

    def get_birdnetpi_config_path(self) -> str:
        """Return the absolute path to the birdnetpi.yaml file."""
        return self.resolve("config", "birdnetpi.yaml")

    def get_static_dir(self) -> str:
        """Return the absolute path to the static files directory."""
        return self.resolve("src", "birdnetpi", "web", "static")

    def get_templates_dir(self) -> str:
        """Return the absolute path to the templates directory."""
        return self.resolve("src", "birdnetpi", "web", "templates")

    def get_fifo_base_path(self) -> str:
        """Return the base path for FIFOs, /dev/shm in Docker, /tmp otherwise."""
        if os.path.exists("/.dockerenv"):
            return "/dev/shm"
        else:
            return "/tmp"

    def get_detection_audio_path(self, species: str, timestamp: datetime) -> str:
        """Return the relative path for a detection audio file."""
        # Format: detections/species_timestamp.wav
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{species.replace(' ', '_')}_{timestamp_str}.wav"
        return os.path.join("detections", filename)
