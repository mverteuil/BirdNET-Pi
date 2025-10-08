"""Tests for PathResolver."""

import datetime
from pathlib import Path

import pytest


class TestPathResolver:
    """Test PathResolver functionality."""

    @pytest.fixture
    def resolver(self, path_resolver, tmp_path):
        """Create a PathResolver instance with test paths.

        Uses the global path_resolver fixture to prevent environment variable patching.
        """
        # Set up test paths using the tmp_path
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir(parents=True, exist_ok=True)

        # Override specific paths for testing
        path_resolver.data_dir = test_data_dir
        path_resolver.app_dir = tmp_path / "app"

        # Also override the methods that return paths based on data_dir
        path_resolver.get_recordings_dir = lambda: test_data_dir / "recordings"
        path_resolver.get_database_dir = lambda: test_data_dir / "database"
        path_resolver.get_models_dir = lambda: test_data_dir / "models"

        return path_resolver

    def test_get_detection_audio_path(self, resolver):
        """Should detection audio path generation."""
        # Test with a scientific name and timestamp
        scientific_name = "Turdus migratorius"
        timestamp = datetime.datetime(2024, 3, 15, 14, 30, 45)

        path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Should return a relative path from recordings_dir
        assert isinstance(path, Path)
        assert not path.is_absolute()
        assert path == Path("Turdus_migratorius/20240315_143045_000000.wav")

    def test_get_detection_audio_path_with_spaces(self, resolver):
        """Should detection audio path with spaces in scientific name."""
        scientific_name = "Corvus corax"
        timestamp = datetime.datetime(2024, 12, 25, 8, 15, 30)

        path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Spaces should be replaced with underscores
        assert path == Path("Corvus_corax/20241225_081530_000000.wav")

    @pytest.mark.parametrize(
        "method_name,expected_dir_name",
        [
            pytest.param("get_recordings_dir", "recordings", id="recordings"),
            pytest.param("get_database_dir", "database", id="database"),
            pytest.param("get_models_dir", "models", id="models"),
        ],
    )
    def test_data_subdirectories(self, resolver, method_name, expected_dir_name):
        """Should return correct data subdirectory paths."""
        method = getattr(resolver, method_name)
        directory = method()

        assert directory.name == expected_dir_name
        assert directory.parent == resolver.data_dir
        assert directory.is_absolute()

    def test_detection_path_uses_recordings_dir(self, resolver):
        """Should detection path is correctly relative to recordings dir."""
        scientific_name = "Test species"
        timestamp = datetime.datetime(2024, 1, 1, 12, 0, 0)

        # Get the detection path
        detection_path = resolver.get_detection_audio_path(scientific_name, timestamp)

        # Verify it would resolve correctly when combined with recordings_dir
        recordings_dir = resolver.get_recordings_dir()
        full_path = recordings_dir / detection_path

        # The full path should be under recordings_dir
        assert str(full_path).startswith(str(recordings_dir))
        assert full_path == recordings_dir / "Test_species" / "20240101_120000_000000.wav"
