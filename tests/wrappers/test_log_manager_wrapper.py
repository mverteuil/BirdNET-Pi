from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.log_manager_wrapper import main_cli


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
        self.model = "mock_model"
        self.sf_thresh = 0.1
        self.confidence = 0.7
        self.sensitivity = 1.0
        self.latitude = 0.0
        self.longitude = 0.0
        self.week = 1
        self.overlap = 0.5
        self.cutoff = 0.5
        self.privacy_threshold = 0.5


@pytest.fixture
def mock_dependencies(monkeypatch, tmp_path):
    """Fixture to mock all external dependencies for this test module."""
    fake_config = FakeConfig(
        db_path=str(tmp_path / "test.db"),
        recordings_dir=str(tmp_path / "recordings"),
    )

    monkeypatch.setattr(
        "birdnetpi.utils.config_file_parser.ConfigFileParser.load_config",
        lambda self: fake_config,
    )

    mock_log_manager_class = MagicMock()
    monkeypatch.setattr("birdnetpi.wrappers.log_manager_wrapper.LogService", mock_log_manager_class)

    yield {"mock_log_manager_class": mock_log_manager_class}


def test_get_logs_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate LogService and call get_logs."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="get_logs", limit=100),
    ):
        main_cli()

        mock_dependencies["mock_log_manager_class"].assert_called_once()
        instance = mock_dependencies["mock_log_manager_class"].return_value
        instance.get_logs.assert_called_once_with()
