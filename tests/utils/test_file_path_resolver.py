"""Tests for FilePathResolver."""

import datetime
from pathlib import Path

import pytest


class TestFilePathResolver:
    """Test FilePathResolver functionality."""

    @pytest.fixture
    def resolver(self, file_path_resolver, tmp_path):
        """Create a FilePathResolver instance with test paths.

        Uses the global file_path_resolver fixture to prevent environment variable patching.
        """
        # Set up test paths using the tmp_path
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir(parents=True, exist_ok=True)

        # Override specific paths for testing
        file_path_resolver.data_dir = test_data_dir
        file_path_resolver.app_dir = tmp_path / "app"

        # Also override the methods that return paths based on data_dir
        file_path_resolver.get_recordings_dir = lambda: test_data_dir / "recordings"
        file_path_resolver.get_database_dir = lambda: test_data_dir / "database"
        file_path_resolver.get_models_dir = lambda: test_data_dir / "models"

        return file_path_resolver

    def test_get_detection_audio_path(self, resolver):
        """Test detection audio path generation."""
        # Test with a scientific name and timestamp
        scientific_name = "Turdus migratorius"
        timestamp = datetime.datetime(2024, 3, 15, 14, 30, 45)

        path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Should return a relative path from data_dir
        assert isinstance(path, Path)
        assert not path.is_absolute()
        assert path == Path("recordings/Turdus_migratorius/20240315_143045.wav")

    def test_get_detection_audio_path_with_spaces(self, resolver):
        """Test detection audio path with spaces in scientific name."""
        scientific_name = "Corvus corax"
        timestamp = datetime.datetime(2024, 12, 25, 8, 15, 30)

        path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Spaces should be replaced with underscores
        assert path == Path("recordings/Corvus_corax/20241225_081530.wav")

    def test_get_recordings_dir(self, resolver):
        """Test recordings directory path."""
        recordings_dir = resolver.get_recordings_dir()

        assert recordings_dir.name == "recordings"
        assert recordings_dir.parent == resolver.data_dir
        assert recordings_dir.is_absolute()

    def test_get_database_dir(self, resolver):
        """Test database directory path."""
        db_dir = resolver.get_database_dir()

        assert db_dir.name == "database"
        assert db_dir.parent == resolver.data_dir
        assert db_dir.is_absolute()

    def test_get_models_dir(self, resolver):
        """Test models directory path."""
        models_dir = resolver.get_models_dir()

        assert models_dir.name == "models"
        assert models_dir.parent == resolver.data_dir
        assert models_dir.is_absolute()

    def test_detection_path_uses_recordings_dir(self, resolver):
        """Test that detection path is correctly relative to recordings dir."""
        scientific_name = "Test species"
        timestamp = datetime.datetime(2024, 1, 1, 12, 0, 0)

        # Get the detection path
        detection_path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Verify it would resolve correctly when combined with data_dir
        full_path = resolver.data_dir / detection_path
        recordings_dir = resolver.get_recordings_dir()

        # The full path should be under recordings_dir
        assert str(full_path).startswith(str(recordings_dir))
        assert full_path == recordings_dir / "Test_species" / "20240101_120000.wav"
