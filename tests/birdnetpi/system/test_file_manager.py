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


@pytest.mark.parametrize(
    "method,path,setup_action,expected_result",
    [
        pytest.param(
            "delete_file",
            Path("test_delete.txt"),
            lambda fm, p: (fm.base_path / p).write_text("Delete me."),
            lambda fm, p: not (fm.base_path / p).exists(),
            id="delete_existing_file",
        ),
        pytest.param(
            "delete_file",
            Path("non_existent_file.txt"),
            None,
            lambda fm, p: not (fm.base_path / p).exists(),
            id="delete_non_existent_file",
        ),
        pytest.param(
            "delete_directory",
            Path("dir_to_delete"),
            lambda fm, p: [
                (fm.base_path / p).mkdir(),
                (fm.base_path / p / "file.txt").write_text("content"),
            ],
            lambda fm, p: not (fm.base_path / p).exists(),
            id="delete_existing_directory",
        ),
        pytest.param(
            "delete_directory",
            Path("non_existent_dir"),
            None,
            lambda fm, p: not (fm.base_path / p).exists(),
            id="delete_non_existent_directory",
        ),
    ],
)
def test_delete_operations(file_manager, method, path, setup_action, expected_result):
    """Should handle file and directory deletion operations correctly."""
    # Setup: create file or directory if needed
    if setup_action:
        result = setup_action(file_manager, path)
        if isinstance(result, list):
            for _action in result:
                pass  # Actions already executed in list comprehension

    # Execute deletion
    getattr(file_manager, method)(path)

    # Verify result
    assert expected_result(file_manager, path)


def test_list_directory_files(file_manager):
    """Should list files in a directory"""
    (file_manager.base_path / "file1.txt").write_text("")
    (file_manager.base_path / "file2.txt").write_text("")
    files = file_manager.list_directory_contents(Path("."))
    assert "file1.txt" in files
    assert "file2.txt" in files


@pytest.mark.parametrize(
    "dir_path,setup_action,expected",
    [
        pytest.param(
            Path("empty_dir"),
            lambda fm, p: (fm.base_path / p).mkdir(),
            [],
            id="empty_directory",
        ),
        pytest.param(
            Path("non_existent_dir"),
            None,
            [],
            id="non_existent_directory",
        ),
    ],
)
def test_list_directory_contents_edge_cases(file_manager, dir_path, setup_action, expected):
    """Should handle edge cases when listing directory contents."""
    # Setup if needed
    if setup_action:
        setup_action(file_manager, dir_path)

    # Execute and verify
    contents = file_manager.list_directory_contents(dir_path)
    assert contents == expected


@pytest.mark.parametrize(
    "method,path,setup_action,expected",
    [
        ("file_exists", Path("existing_file.txt"), "create_file", True),
        ("file_exists", Path("non_existing_file.txt"), None, False),
        ("directory_exists", Path("existing_dir"), "create_dir", True),
        ("directory_exists", Path("non_existing_dir"), None, False),
    ],
    ids=[
        "file_exists_when_present",
        "file_exists_when_missing",
        "directory_exists_when_present",
        "directory_exists_when_missing",
    ],
)
def test_existence_checks(file_manager, method, path, setup_action, expected):
    """Should correctly report file/directory existence for various scenarios."""
    # Setup: create file or directory if needed
    if setup_action == "create_file":
        (file_manager.base_path / path).write_text("content")
    elif setup_action == "create_dir":
        (file_manager.base_path / path).mkdir()

    # Execute and verify
    result = getattr(file_manager, method)(path)
    assert result is expected


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
