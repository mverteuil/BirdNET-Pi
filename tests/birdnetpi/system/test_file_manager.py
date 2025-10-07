from pathlib import Path
from unittest.mock import ANY, patch

import numpy as np
import pytest

from birdnetpi.detections.models import AudioFile
from birdnetpi.system.file_manager import FileManager


@pytest.fixture
def file_manager(path_resolver, tmp_path):
    """Provide a FileManager instance for testing.

    Uses the global path_resolver fixture as a base to prevent MagicMock file creation.
    """
    # Override the data_dir to use tmp_path
    path_resolver.data_dir = tmp_path
    return FileManager(path_resolver=path_resolver)


def test_create_directory(file_manager):
    """Should create a directory if it doesn't exist"""
    test_dir = Path("test_dir")
    file_manager.create_directory(test_dir)
    assert (file_manager.base_path / test_dir).is_dir()


def test_write_file(file_manager):
    """Should write content to a file"""
    file_path = Path("test_file.txt")
    content = "Hello, world!"
    file_manager.write_file(file_path, content)
    assert (file_manager.base_path / file_path).read_text() == content


def test_read_file(file_manager):
    """Should read content from a file"""
    file_path = Path("test_read.txt")
    content = "Read this."
    (file_manager.base_path / file_path).write_text(content)
    read_content = file_manager.read_file(file_path)
    assert read_content == content


def test_delete_file(file_manager):
    """Should delete a file"""
    file_path = Path("test_delete.txt")
    (file_manager.base_path / file_path).write_text("Delete me.")
    file_manager.delete_file(file_path)
    assert not (file_manager.base_path / file_path).exists()


def test_list_directory_files(file_manager):
    """Should list files in a directory"""
    (file_manager.base_path / "file1.txt").write_text("")
    (file_manager.base_path / "file2.txt").write_text("")
    files = file_manager.list_directory_contents(Path("."))
    assert "file1.txt" in files
    assert "file2.txt" in files


def test_delete_file_non_existent(file_manager):
    """Should not raise an error when deleting a non-existent file"""
    file_path = Path("non_existent_file.txt")
    file_manager.delete_file(file_path)
    assert not (file_manager.base_path / file_path).exists()


def test_delete_directory(file_manager):
    """Should delete a directory and its contents"""
    test_dir = Path("dir_to_delete")
    (file_manager.base_path / test_dir).mkdir()
    (file_manager.base_path / test_dir / "file.txt").write_text("content")
    file_manager.delete_directory(test_dir)
    assert not (file_manager.base_path / test_dir).exists()


def test_delete_directory_non_existent(file_manager):
    """Should not raise an error when deleting a non-existent directory"""
    test_dir = Path("non_existent_dir")
    file_manager.delete_directory(test_dir)
    assert not (file_manager.base_path / test_dir).exists()


def test_list_directory_contents_empty(file_manager):
    """Should return an empty list for an empty directory"""
    test_dir = Path("empty_dir")
    (file_manager.base_path / test_dir).mkdir()
    contents = file_manager.list_directory_contents(test_dir)
    assert contents == []


def test_list_directory_contents_non_existent(file_manager):
    """Should return an empty list for a non-existent directory"""
    test_dir = Path("non_existent_dir")
    contents = file_manager.list_directory_contents(test_dir)
    assert contents == []


def test_file_exists_true(file_manager):
    """Should return True if the file exists"""
    file_path = Path("existing_file.txt")
    (file_manager.base_path / file_path).write_text("content")
    assert file_manager.file_exists(file_path) is True


def test_file_exists_false(file_manager):
    """Should return False if the file does not exist"""
    file_path = Path("non_existing_file.txt")
    assert file_manager.file_exists(file_path) is False


def test_directory_exists_true(file_manager):
    """Should return True if the directory exists"""
    test_dir = Path("existing_dir")
    (file_manager.base_path / test_dir).mkdir()
    assert file_manager.directory_exists(test_dir) is True


def test_directory_exists_false(file_manager):
    """Should return False if the directory does not exist"""
    test_dir = Path("non_existing_dir")
    assert file_manager.directory_exists(test_dir) is False


def test_save_detection_audio(file_manager):
    """Should save audio bytes to a WAV file and return AudioFile instance (covers lines 79-90)"""
    # Mock soundfile.write
    with patch("birdnetpi.system.file_manager.sf.write", autospec=True) as mock_sf_write:
        # Prepare test data
        relative_path = Path("detections/test_audio.wav")
        raw_audio_bytes = b"\x00\x01" * 1000  # 2000 bytes of audio data
        sample_rate = 44100
        channels = 1

        # Call the method
        result = file_manager.save_detection_audio(
            relative_path=relative_path,
            raw_audio_bytes=raw_audio_bytes,
            sample_rate=sample_rate,
            channels=channels,
        )

        # Verify soundfile.write was called correctly
        # The path should be relative to recordings directory, not base_path
        recordings_dir = file_manager.path_resolver.get_recordings_dir()
        expected_full_path = recordings_dir / relative_path
        # The second argument will be a numpy array, so we use ANY
        mock_sf_write.assert_called_once_with(
            str(expected_full_path), ANY, sample_rate, subtype="PCM_16"
        )

        # Verify the numpy array conversion is correct
        call_args = mock_sf_write.call_args[0]
        audio_array_arg = call_args[1]
        assert isinstance(audio_array_arg, np.ndarray)
        assert audio_array_arg.dtype == np.int16
        assert len(audio_array_arg) == 1000  # 2000 bytes / 2 bytes per int16

        # Verify the directory was created (inside recordings dir)
        assert (recordings_dir / "detections").exists()

        # Verify the returned AudioFile object
        assert isinstance(result, AudioFile)
        assert result.file_path == relative_path
        # recording_start_time field has been removed as redundant
        assert result.size_bytes == 2000  # len(raw_audio_bytes)  # type: ignore[operator]

        # Calculate expected duration: len(bytes) / (sample_rate * channels * 2)
        # 2000 / (44100 * 1 * 2) = 2000 / 88200 ≈ 0.02268
        expected_duration = 2000 / (44100 * 1 * 2)
        assert abs(float(result.duration) - expected_duration) < 0.0001  # type: ignore[arg-type]
