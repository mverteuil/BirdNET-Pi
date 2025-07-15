from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.update_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with patch(
        "birdnetpi.wrappers.update_manager_wrapper.UpdateManager"
    ) as mock_update_manager:
        yield {"mock_update_manager": mock_update_manager}


def test_update_birdnet_action(mock_dependencies):
    """Should call update_birdnet when action is 'update_birdnet'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="update_birdnet", remote="origin", branch="main"),
    ):
        main_cli()
        mock_dependencies[
            "mock_update_manager"
        ].return_value.update_birdnet.assert_called_once_with(
            remote="origin", branch="main"
        )


def test_update_caddyfile_action(mock_dependencies):
    """Should call update_caddyfile when action is 'update_caddyfile'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="update_caddyfile",
            birdnetpi_url="test_url",
            extracted_path="test_path",
            caddy_pwd="test_pwd",
        ),
    ):
        main_cli()
        mock_dependencies[
            "mock_update_manager"
        ].return_value.update_caddyfile.assert_called_once_with(
            birdnetpi_url="test_url", extracted_path="test_path", caddy_pwd="test_pwd"
        )


def test_unknown_action_raises_error(mock_dependencies):
    """Should raise an error for an unknown action."""
    with (
        patch(
            "argparse.ArgumentParser.parse_args",
            return_value=MagicMock(action="unknown_action"),
        ),
        patch("argparse.ArgumentParser.error") as mock_error,
    ):
        main_cli()
        mock_error.assert_called_once_with("Unknown action: unknown_action")
