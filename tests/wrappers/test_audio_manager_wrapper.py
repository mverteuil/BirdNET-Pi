from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.wrappers.audio_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch, tmp_path):
    """Fixture to mock all external dependencies for this test module."""
    mock_audio_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.audio_manager_wrapper.AudioManager",
        mock_audio_manager_class,
    )

    mock_file_path_resolver = FilePathResolver()
    mock_file_path_resolver.repo_root = str(tmp_path)
    monkeypatch.setattr(
        "birdnetpi.wrappers.audio_manager_wrapper.FilePathResolver",
        lambda: mock_file_path_resolver,
    )

    yield {"mock_audio_manager_class": mock_audio_manager_class}


def test_record_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate AudioManager and call record."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="record"),
    ):
        main_cli()

        mock_dependencies["mock_audio_manager_class"].assert_called_once()
        instance = mock_dependencies["mock_audio_manager_class"].return_value
        instance.record.assert_called_once()
