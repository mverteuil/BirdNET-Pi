from unittest.mock import DEFAULT, MagicMock, patch

import pytest

import birdnetpi.wrappers.generate_dummy_data as gdd
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Mock external dependencies for generate_dummy_data.py."""
    with patch.multiple(
        "birdnetpi.wrappers.generate_dummy_data",
        FilePathResolver=DEFAULT,
        DatabaseService=DEFAULT,
        DetectionManager=DEFAULT,
        generate_dummy_detections=DEFAULT,
    ) as mocks:
        # Configure mocks
        mocks["FilePathResolver"].return_value.get_database_path.return_value = "/tmp/test.db"
        mocks["DatabaseService"].return_value = MagicMock(spec=DatabaseService)
        mocks["DetectionManager"].return_value = MagicMock(spec=DetectionManager)
        mocks["generate_dummy_detections"].return_value = None

        # Yield mocks for individual test configuration
        yield mocks


class TestGenerateDummyData:
    """Test the generate_dummy_data wrapper."""

    def test_main_database_exists_and_has_data(self, mocker, mock_dependencies, capsys):
        """Should skip dummy data generation if database exists and has data."""
        mock_os = mocker.patch("birdnetpi.wrappers.generate_dummy_data.os")
        mock_os.path.exists.return_value = True
        mock_os.path.getsize.return_value = 100  # Simulate non-empty file
        mock_dependencies["DetectionManager"].return_value.get_all_detections.return_value = [
            "detection1"
        ]

        gdd.main()

        captured = capsys.readouterr()
        assert "Database already contains data. Skipping dummy data generation." in captured.out
        mock_dependencies["generate_dummy_detections"].assert_not_called()

    def test_main_database_exists_but_is_empty(self, mocker, mock_dependencies, capsys):
        """Should generate dummy data if database exists but is empty."""
        mock_os = mocker.patch("birdnetpi.wrappers.generate_dummy_data.os")
        mock_os.path.exists.return_value = True
        mock_os.path.getsize.return_value = 0  # Simulate empty file
        mock_dependencies["DetectionManager"].return_value.get_all_detections.return_value = []

        gdd.main()

        captured = capsys.readouterr()
        assert "Database is empty or does not exist. Generating dummy data..." in captured.out
        assert "Dummy data generation complete." in captured.out
        mock_dependencies["generate_dummy_detections"].assert_called_once()

    def test_main_database_does_not_exist(self, mocker, mock_dependencies, capsys):
        """Should generate dummy data if database does not exist."""
        mock_os = mocker.patch("birdnetpi.wrappers.generate_dummy_data.os")
        mock_os.path.exists.return_value = False

        gdd.main()

        captured = capsys.readouterr()
        assert "Database is empty or does not exist. Generating dummy data..." in captured.out
        assert "Dummy data generation complete." in captured.out
        mock_dependencies["generate_dummy_detections"].assert_called_once()
