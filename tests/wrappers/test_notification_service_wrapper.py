from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.notification_service_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with (
        patch(
            "birdnetpi.wrappers.notification_service_wrapper.NotificationService"
        ) as mock_notification_service,
        patch(
            "birdnetpi.wrappers.notification_service_wrapper.FilePathResolver"
        ) as mock_file_path_resolver,
        patch(
            "birdnetpi.wrappers.notification_service_wrapper.ConfigFileParser"
        ) as mock_config_file_parser,
    ):
        mock_file_path_resolver_instance = mock_file_path_resolver.return_value
        mock_file_path_resolver_instance.get_birdnet_pi_config_path.return_value = str(
            tmp_path / "birdnet_pi_config.yaml"
        )
        (tmp_path / "birdnet_pi_config.yaml").touch()
        yield {
            "mock_notification_service": mock_notification_service,
            "mock_file_path_resolver": mock_file_path_resolver,
            "mock_config_file_parser": mock_config_file_parser,
        }


def test_species_notifier_action(mock_dependencies):
    """Should call species_notifier when action is 'species_notifier'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="species_notifier", species_name="test_species", confidence=0.9
        ),
    ):
        main_cli()
        mock_dependencies[
            "mock_notification_service"
        ].return_value.species_notifier.assert_called_once_with("test_species", 0.9)


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
