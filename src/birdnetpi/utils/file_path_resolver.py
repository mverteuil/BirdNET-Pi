import os


class FilePathResolver:
    """Resolves absolute file paths within the BirdNET-Pi project structure."""

    def __init__(self) -> None:
        # Determine the repository root dynamically
        # This file is in BirdNET-Pi/src/birdnetpi/utils/
        # So, go up three directories to reach BirdNET-Pi/
        self.base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )

    def resolve(self, *paths: str) -> str:
        """Resolve an absolute path from the base directory and given subpaths."""
        return os.path.join(self.base_dir, *paths)

    def get_birds_db_path(self) -> str:
        """Return the absolute path to the birds.db file."""
        return self.resolve("scripts", "birds.db")

    def get_extracted_birdsounds_path(self) -> str:
        """Return the absolute path to the extracted birdsounds directory."""
        return self.resolve("BirdSongs", "Extracted", "By_Date")

    def get_birdnet_conf_path(self) -> str:
        """Return the absolute path to the birdnet.conf file."""
        return self.resolve("config", "birdnet.conf")

    def get_birdnet_pi_config_path(self) -> str:
        """Return the absolute path to the birdnet_pi_config.yaml file."""
        return self.resolve("config", "birdnet_pi_config.yaml")
