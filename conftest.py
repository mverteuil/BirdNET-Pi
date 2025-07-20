from pathlib import Path

import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with a temporary base directory."""
    # Create a temporary directory for the repo root
    repo_root = tmp_path / "BirdNET-Pi"
    repo_root.mkdir()

    # Create a mock FilePathResolver that uses the temporary directory
    resolver = FilePathResolver()
    resolver.base_dir = str(repo_root)
    return resolver
