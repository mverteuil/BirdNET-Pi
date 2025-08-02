from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with a temporary base directory

    Still uses the legitimate templates and static files directories.
    """
    # Create a temporary directory for the repo root
    repo_root = tmp_path / "BirdNET-Pi"
    repo_root.mkdir()

    # Create a real FilePathResolver to get actual static and template paths
    real_resolver = FilePathResolver()

    # Create a MagicMock for FilePathResolver
    mock_resolver = MagicMock(spec=FilePathResolver)

    # Set base_dir to the temporary repo root
    mock_resolver.base_dir = str(repo_root)

    # Mock methods that should return paths within the temporary directory
    mock_resolver.get_birds_db_path.return_value = str(repo_root / "scripts" / "birds.db")
    mock_resolver.get_birdnet_pi_config_path.return_value = str(
        repo_root / "config" / "birdnet_pi_config.yaml"
    )
    mock_resolver.get_extracted_birdsounds_path.return_value = str(
        repo_root / "BirdSongs" / "Extracted" / "By_Date"
    )

    # Use the real methods for static and templates directories
    mock_resolver.get_static_dir.side_effect = real_resolver.get_static_dir
    mock_resolver.get_templates_dir.side_effect = real_resolver.get_templates_dir

    # Ensure the resolve method works with the mocked base_dir
    mock_resolver.resolve.side_effect = lambda *paths: str(
        Path(mock_resolver.base_dir).joinpath(*paths)
    )

    return mock_resolver
