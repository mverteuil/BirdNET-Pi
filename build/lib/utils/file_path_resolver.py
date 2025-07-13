import os


class FilePathResolver:
    def __init__(self):
        # Determine the repository root dynamically
        # This file is in BirdNET-Pi/src/utils/
        # So, go up two directories to reach BirdNET-Pi/
        self.base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

    def resolve(self, *paths: str) -> str:
        """Resolves an absolute path from the base directory and given subpaths."""
        return os.path.join(self.base_dir, *paths)

    def get_birds_db_path(self) -> str:
        """Returns the absolute path to the birds.db file."""
        return self.resolve("scripts", "birds.db")

    def get_extracted_birdsounds_path(self) -> str:
        """Returns the absolute path to the extracted birdsounds directory."""
        return self.resolve("BirdSongs", "Extracted", "By_Date")
