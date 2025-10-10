"""Tests for the notification rules UI functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import providers
from fastapi import status
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.audio.capture import AudioDeviceService
from birdnetpi.config.manager import ConfigManager
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def app_with_notification_rules(path_resolver, repo_root, mock_config_with_rules):
    """Create app with notification rules config."""
    # Create temporary config file
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = Path(temp_dir) / "config.yml"
        config_file.touch()

        # Mock path resolver methods
        path_resolver.get_birdnetpi_config_path = lambda: config_file
        path_resolver.get_static_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "static"
        path_resolver.get_templates_dir = (
            lambda: repo_root / "src" / "birdnetpi" / "web" / "templates"
        )

        # Mock ConfigManager
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_config_manager.load.return_value = mock_config_with_rules
        mock_config_manager.save.return_value = None
        mock_config_manager.config_path = config_file

        # Mock AudioDeviceService
        mock_audio_service = MagicMock(spec=AudioDeviceService)
        mock_audio_service.discover_input_devices.return_value = []

        # Override providers BEFORE creating the app
        Container.path_resolver.override(providers.Singleton(lambda: path_resolver))

        # Create templates
        templates_dir = path_resolver.get_templates_dir()
        templates = Jinja2Templates(directory=str(templates_dir))
        Container.templates.override(providers.Singleton(lambda: templates))

        # Patch classes during app creation
        with (
            patch(
                "birdnetpi.web.routers.settings_view_routes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch(
                "birdnetpi.web.routers.settings_view_routes.AudioDeviceService",
                return_value=mock_audio_service,
            ),
            patch(
                "birdnetpi.web.routers.settings_view_routes.PathResolver",
                return_value=path_resolver,
            ),
            patch("birdnetpi.web.routers.sqladmin_view_routes.setup_sqladmin", autospec=True),
        ):
            app = create_app()
            yield app, mock_config_manager, mock_audio_service

        # Clean up overrides
        Container.path_resolver.reset_override()
        Container.templates.reset_override()


@pytest.fixture
def client_with_notification_rules(app_with_notification_rules):
    """Create test client with notification rules."""
    app, config_manager, audio_service = app_with_notification_rules
    with TestClient(app) as test_client:
        yield test_client, config_manager, audio_service


def test_settings_page_renders_notification_rules(
    client_with_notification_rules, mock_config_with_rules
):
    """Should render notification rules correctly on the settings page."""
    client, _config_manager, _ = client_with_notification_rules
    response = client.get("/admin/settings")
    assert response.status_code == status.HTTP_200_OK

    # Check that notification rules elements are present
    assert "Notification Rules" in response.text
    assert "Apprise Targets" in response.text
    assert "Webhook Targets" in response.text
    assert "addNotificationRule" in response.text


def test_post_settings_view_with_notification_rules(
    client_with_notification_rules, mock_config_with_rules
):
    """Should successfully post settings with notification rules data."""
    client, config_manager, _ = client_with_notification_rules

    # Prepare form data with notification rules
    form_data = {
        "site_name": "Test Site",
        "latitude": "0.0",
        "longitude": "0.0",
        "model": "test.tflite",
        "metadata_model": "test_metadata.tflite",
        "species_confidence_threshold": "0.03",
        "sensitivity": "1.25",
        "week": "-1",
        "audio_format": "wav",
        "extraction_length": "3.0",
        "audio_device_index": "-1",
        "sample_rate": "48000",
        "audio_channels": "1",
        "analysis_overlap": "0.5",
        "birdweather_id": "",
        "apprise_targets_json": json.dumps({"discord": "discord://webhook/token"}),
        "webhook_targets_json": json.dumps({"home_assistant": "http://ha.local/webhook"}),
        "notification_rules_json": json.dumps(
            [
                {
                    "name": "Test Rule",
                    "enabled": True,
                    "service": "apprise",
                    "target": "discord",
                    "frequency": {"when": "immediate"},
                    "scope": "new_ever",
                    "include_taxa": {"species": ["Turdus migratorius"]},
                    "exclude_taxa": {"species": []},
                }
            ]
        ),
        "flickr_api_key": "",
        "flickr_filter_email": "",
        "language": "en",
        "species_display_mode": "full",
        "timezone": "UTC",
        "enable_gps": "false",
        "gps_update_interval": "5.0",
        "hardware_check_interval": "10.0",
        "enable_audio_device_check": "true",
        "enable_system_resource_check": "true",
        "enable_gps_check": "false",
        "privacy_threshold": "10.0",
        "enable_mqtt": "false",
        "mqtt_broker_host": "localhost",
        "mqtt_broker_port": "1883",
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": "birdnet",
        "mqtt_client_id": "birdnet-pi",
        "enable_webhooks": "false",
        "webhook_urls": "",
        "webhook_events": "detection,health,gps,system",
    }

    response = client.post("/admin/settings", data=form_data, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER

    # Verify save was called
    config_manager.save.assert_called_once()

    # Check the saved config has correct notification data
    saved_config = config_manager.save.call_args[0][0]
    assert saved_config.apprise_targets == {"discord": "discord://webhook/token"}
    assert saved_config.webhook_targets == {"home_assistant": "http://ha.local/webhook"}
    assert len(saved_config.notification_rules) == 1
    assert saved_config.notification_rules[0]["name"] == "Test Rule"


@pytest.fixture
def mock_config_with_rules():
    """Create a mock config with notification rules."""
    return BirdNETConfig(
        site_name="Test Site",
        apprise_targets={"discord": "discord://webhook/token"},
        webhook_targets={"home_assistant": "http://ha.local/webhook"},
        notification_rules=[
            {
                "name": "Rare Birds",
                "enabled": True,
                "service": "apprise",
                "target": "discord",
                "frequency": {"when": "immediate"},
                "scope": "new_ever",
                "include_taxa": {"species": ["Turdus migratorius"]},
                "exclude_taxa": {"species": ["Passer domesticus"]},
                "minimum_confidence": 80,
                "title_template": "New bird: {{ common_name }}",
                "body_template": "",
            }
        ],
    )
