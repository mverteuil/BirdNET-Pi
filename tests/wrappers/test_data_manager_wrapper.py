from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.data_manager_wrapper import main_cli


# Define simple, explicit "Fake" objects for the test
class FakeDataConfig:
    """A fake DataConfig for testing."""

    def __init__(self, db_path, recordings_dir):
        self.db_path = db_path
        self.recordings_dir = recordings_dir


class FakeConfig:
    """A fake BirdNETConfig for testing."""

    def __init__(self, db_path, recordings_dir):
        self.data = FakeDataConfig(db_path, recordings_dir)


@pytest.fixture
def mock_dependencies(tmp_path, monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    fake_config = FakeConfig(
        db_path=str(tmp_path / "test.db"),
        recordings_dir=str(tmp_path / "recordings"),
    )

    monkeypatch.setattr(
        "birdnetpi.utils.config_file_parser.ConfigFileParser.load_config",
        lambda self: fake_config,
    )

    mock_data_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.data_manager_wrapper.DataManager", mock_data_manager_class
    )

    mock_db_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.data_manager_wrapper.DatabaseService",
        mock_db_service_class,
    )

    mock_file_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.data_manager_wrapper.FileManager", mock_file_manager_class
    )

    mock_service_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.data_manager_wrapper.SystemControlService",
        mock_service_manager_class,
    )

    yield {
        "mock_data_manager_class": mock_data_manager_class,
        "mock_db_service_class": mock_db_service_class,
        "mock_file_manager_class": mock_file_manager_class,
        "mock_service_manager_class": mock_service_manager_class,
        "fake_config": fake_config,
    }


def test_cleanup_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate DataManager and call cleanup_processed_files."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="cleanup"),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_data_manager_class"].assert_called_once_with(
            mock_dependencies["fake_config"],
            mock_dependencies["mock_file_manager_class"].return_value,
            mock_dependencies["mock_db_service_class"].return_value,
            mock_dependencies["mock_service_manager_class"].return_value,
        )

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_data_manager_class"].return_value
        instance.cleanup_processed_files.assert_called_once()


def test_clear_all_data_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate DataManager and call clear_all_data."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="clear_all_data"),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_data_manager_class"].assert_called_once_with(
            mock_dependencies["fake_config"],
            mock_dependencies["mock_file_manager_class"].return_value,
            mock_dependencies["mock_db_service_class"].return_value,
            mock_dependencies["mock_service_manager_class"].return_value,
        )

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_data_manager_class"].return_value
        instance.clear_all_data.assert_called_once()
