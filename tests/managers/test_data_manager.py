import os
from unittest.mock import Mock, patch

import pytest

from managers.data_manager import DataManager
from models.birdnet_config import BirdNETConfig, DataConfig
from services.database_manager import DatabaseManager
from services.file_manager import FileManager


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance with mock data paths."""
    config = Mock(spec=BirdNETConfig)
    config.data = Mock(spec=DataConfig)
    config.data.processed_dir = "/mock/processed"
    config.data.recordings_dir = "/mock/recordings"
    config.data.id_file = "/mock/id.txt"
    config.data.extracted_dir = "/mock/extracted"
    return config


@pytest.fixture
def mock_file_manager(mock_config):
    """Provide a mock FileManager instance with get_full_path side effect."""
    fm = Mock(spec=FileManager)
    # Simulate get_full_path behavior: it should return the absolute path
    fm.get_full_path.side_effect = lambda p: p
    return fm


@pytest.fixture
def mock_database_manager():
    """Provide a mock DatabaseManager instance."""
    return Mock(spec=DatabaseManager)


@pytest.fixture
def data_manager(mock_config, mock_file_manager, mock_database_manager):
    """Provide a DataManager instance with mocked dependencies."""
    return DataManager(
        config=mock_config,
        file_manager=mock_file_manager,
        database_manager=mock_database_manager,
    )


def test_cleanup_processed_files_empty_csv(
    data_manager, mock_file_manager, mock_config
):
    """Should delete empty CSV files and their corresponding WAV files"""
    mock_file_manager.list_directory_contents.return_value = [
        "test.csv",
        "another.csv",
    ]
    mock_file_manager.file_exists.return_value = True  # Assume WAV file exists

    with patch("managers.data_manager.os.path.getsize") as mock_getsize:
        mock_getsize.side_effect = lambda x: 57 if x.endswith(".csv") else 100
        with patch("managers.data_manager.os.path.getmtime", return_value=1.0):
            data_manager.cleanup_processed_files()

    mock_file_manager.delete_file.assert_any_call("/mock/processed/test.csv")
    mock_file_manager.delete_file.assert_any_call("/mock/processed/test")
    mock_file_manager.delete_file.assert_any_call("/mock/processed/another.csv")
    mock_file_manager.delete_file.assert_any_call("/mock/processed/another")
    assert mock_file_manager.delete_file.call_count == 4


def test_cleanup_processed_files_limit_exceeded(
    data_manager, mock_file_manager, mock_config
):
    """Should delete oldest files when processed file limit is exceeded"""
    # Create more than 100 files, ensuring they are not considered 'empty'
    files = [f"file_{i}.csv" for i in range(120)]
    files.extend([f"file_{i}.wav" for i in range(120)])
    mock_file_manager.list_directory_contents.return_value = files

    # Mock getmtime to simulate different modification times
    with patch("managers.data_manager.os.path.getmtime") as mock_getmtime:
        # Assign unique mtimes to ensure consistent sorting
        mock_getmtime.side_effect = lambda x: float(x.split("_")[1].split(".")[0])
        # Ensure ALL files are NOT considered empty (size > 57)
        with patch("managers.data_manager.os.path.getsize", return_value=1000):
            data_manager.cleanup_processed_files()

    # Expect 20 oldest files (csv and wav) to be deleted
    expected_deletions = [
        os.path.join(mock_config.data.processed_dir, f"file_{i}.csv") for i in range(20)
    ]
    expected_deletions.extend(
        [
            os.path.join(mock_config.data.processed_dir, f"file_{i}.wav")
            for i in range(20)
        ]
    )

    for f in expected_deletions:
        mock_file_manager.delete_file.assert_any_call(f)
    assert mock_file_manager.delete_file.call_count == 140


@patch("managers.data_manager.subprocess.run")
def test_clear_all_data(
    mock_subprocess_run,
    data_manager,
    mock_file_manager,
    mock_database_manager,
    mock_config,
    capsys,
):
    """Should clear all data, stop/start services, and recreate directories"""
    mock_file_manager.file_exists.return_value = True

    data_manager.clear_all_data()

    # Verify services are stopped
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "stop", "birdnet_recording.service"]
    )
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "stop", "birdnet_analysis.service"]
    )
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "stop", "birdnet_server.service"]
    )

    # Verify data removal
    mock_file_manager.delete_directory.assert_called_once_with(
        mock_config.data.recordings_dir
    )
    mock_file_manager.delete_file.assert_called_once_with(mock_config.data.id_file)
    mock_database_manager.clear_database.assert_called_once()

    # Verify directory recreation
    mock_file_manager.create_directory.assert_any_call(mock_config.data.extracted_dir)
    mock_file_manager.create_directory.assert_any_call(
        os.path.join(mock_config.data.extracted_dir, "By_Date")
    )
    mock_file_manager.create_directory.assert_any_call(
        os.path.join(mock_config.data.extracted_dir, "Charts")
    )
    mock_file_manager.create_directory.assert_any_call(mock_config.data.processed_dir)
    assert mock_file_manager.create_directory.call_count == 4

    # Verify services are restarted
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "start", "birdnet_recording.service"]
    )
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "start", "birdnet_analysis.service"]
    )
    mock_subprocess_run.assert_any_call(
        ["sudo", "systemctl", "start", "birdnet_server.service"]
    )

    captured = capsys.readouterr()
    assert "Stopping services..." in captured.out
    assert "Removing all data..." in captured.out
    assert "Re-creating necessary directories..." in captured.out
    assert (
        "Re-establishing symlinks..." in captured.out
    )  # This line is printed by the manager
    assert "Restarting services..." in captured.out
