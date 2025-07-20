from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.notification_service_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    mock_notification_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.notification_service_wrapper.NotificationService",
        mock_notification_service_class,
    )

    yield {"mock_notification_service_class": mock_notification_service_class}


def test_species_notifier_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate NotificationService and call species_notifier."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="species_notifier", species_name="Test Bird", confidence=0.9
        ),
    ):
        main_cli()

        mock_dependencies["mock_notification_service_class"].assert_called_once()
        instance = mock_dependencies["mock_notification_service_class"].return_value
        instance.species_notifier.assert_called_once_with("Test Bird", 0.9)
