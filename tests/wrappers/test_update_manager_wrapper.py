from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.models.git_update_config import GitUpdateConfig
from birdnetpi.wrappers.update_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    mock_update_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.update_manager_wrapper.UpdateManager",
        mock_update_manager_class,
    )

    yield {"mock_update_manager_class": mock_update_manager_class}


def test_update_birdnet_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate UpdateManager and call update_birdnet."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="update_birdnet", remote="origin", branch="main"),
    ):
        main_cli()

        mock_dependencies["mock_update_manager_class"].assert_called_once()
        instance = mock_dependencies["mock_update_manager_class"].return_value
        instance.update_birdnet.assert_called_once_with(
            GitUpdateConfig(remote="origin", branch="main")
        )
