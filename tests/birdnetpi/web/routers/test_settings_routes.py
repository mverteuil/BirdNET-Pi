"""Tests for settings routes including GET and POST functionality."""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import sqladmin
from dependency_injector import providers
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from birdnetpi.audio.devices import AudioDevice, AudioDeviceService
from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.utils.auth import AdminUser, AuthService, pwd_context
from birdnetpi.web.core.container import Container
from birdnetpi.web.core.factory import create_app


@pytest.fixture
def mock_audio_devices():
    """Create mock audio devices for testing."""
    devices = [
        AudioDevice(
            name="USB Audio Device",
            index=0,
            host_api_index=0,
            max_input_channels=2,
            max_output_channels=0,
            default_low_input_latency=0.01,
            default_low_output_latency=0.0,
            default_high_input_latency=0.04,
            default_high_output_latency=0.0,
            default_samplerate=48000.0,
        ),
        AudioDevice(
            name="Built-in Microphone",
            index=1,
            host_api_index=0,
            max_input_channels=1,
            max_output_channels=0,
            default_low_input_latency=0.02,
            default_low_output_latency=0.0,
            default_high_input_latency=0.08,
            default_high_output_latency=0.0,
            default_samplerate=44100.0,
        ),
    ]
    return devices


@pytest.fixture
def test_config():
    """Should create a test configuration."""
    return BirdNETConfig(
        site_name="Test Site",
        latitude=45.5,
        longitude=-73.6,
        sensitivity_setting=1.25,
        species_confidence_threshold=0.7,
        audio_device_index=0,
        sample_rate=48000,
        audio_channels=1,
        audio_overlap=0.5,
        model="BirdNET_GLOBAL_6K_V2.4_Model_FP16",
        metadata_model="BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
        apprise_targets={},
        webhook_targets={},
        notification_rules=[],
        notification_title_default="Test Title",
        notification_body_default="Test Body",
        notify_quiet_hours_start="",
        notify_quiet_hours_end="",
    )


@pytest.fixture
def app_with_settings_routes(path_resolver, repo_root, test_config, mock_audio_devices):
    """Create FastAPI app with settings routes and mocked dependencies."""
    temp_dir = tempfile.mkdtemp(prefix="test_settings_")
    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir(exist_ok=True)
    mock_config_manager = MagicMock(spec=ConfigManager)
    mock_config_manager.load.return_value = test_config
    mock_config_manager.save.return_value = None
    mock_audio_service = MagicMock(spec=AudioDeviceService)
    mock_audio_service.discover_input_devices.return_value = mock_audio_devices

    # Mock AuthService to enable authentication in tests
    mock_auth_service = MagicMock(spec=AuthService)
    mock_auth_service.admin_exists.return_value = True
    mock_admin = AdminUser(
        username="admin",
        password_hash=pwd_context.hash("testpassword"),
        created_at=datetime.now(),
    )
    mock_auth_service.load_admin_user.return_value = mock_admin
    mock_auth_service.verify_password.side_effect = lambda plain, hashed: pwd_context.verify(
        plain, hashed
    )

    path_resolver.get_birdnetpi_config_path = lambda: config_dir / "birdnetpi.yaml"
    path_resolver.get_templates_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "templates"
    path_resolver.get_static_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "static"
    path_resolver.get_models_dir = lambda: repo_root / "models"
    Container.path_resolver.override(providers.Singleton(lambda: path_resolver))
    Container.auth_service.override(providers.Singleton(lambda: mock_auth_service))
    templates_dir = repo_root / "src" / "birdnetpi" / "web" / "templates"
    Container.templates.override(
        providers.Singleton(lambda: Jinja2Templates(directory=str(templates_dir)))
    )
    with (
        patch(
            "birdnetpi.web.routers.settings_view_routes.ConfigManager", autospec=True
        ) as mock_config_mgr_class,
        patch(
            "birdnetpi.web.routers.settings_view_routes.AudioDeviceService",
            autospec=True,
            return_value=mock_audio_service,
        ),
        patch(
            "birdnetpi.web.routers.sqladmin_view_routes.setup_sqladmin",
            autospec=True,
            side_effect=lambda app: Mock(spec=sqladmin.Admin),
        ),
    ):
        mock_config_mgr_class.return_value = mock_config_manager
        app = create_app()
        yield (app, mock_config_manager, mock_audio_service)
    Container.path_resolver.reset_override()
    Container.auth_service.reset_override()
    Container.templates.reset_override()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client_with_mocks(app_with_settings_routes, authenticate_sync_client):
    """Create authenticated test client with mocked dependencies."""
    app, config_manager, audio_service = app_with_settings_routes
    with TestClient(app) as test_client:
        authenticate_sync_client(test_client)
        yield (test_client, config_manager, audio_service)


class TestSettingsGetRoute:
    """Tests for GET /admin/settings endpoint."""

    def test_settings_page_renders_successfully(self, client_with_mocks):
        """Should render settings page with 200 status."""
        client, _, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_settings_page_includes_config_values(self, client_with_mocks, test_config):
        """Should include configuration values in the rendered page."""
        client, _, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert str(test_config.latitude) in response.text
        assert str(test_config.longitude) in response.text
        assert test_config.site_name in response.text

    def test_settings_page_includes_audio_devices(self, client_with_mocks, mock_audio_devices):
        """Should include audio devices in the rendered page."""
        client, _, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        for device in mock_audio_devices:
            assert device.name in response.text

    def test_settings_page_calls_config_manager_load(self, client_with_mocks):
        """Should call ConfigManager.load() to get configuration."""
        client, config_manager, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        config_manager.load.assert_called_once()

    def test_settings_page_calls_audio_service_discover(self, client_with_mocks):
        """Should call AudioDeviceService.discover_input_devices()."""
        client, _, audio_service = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        audio_service.discover_input_devices.assert_called_once()

    def test_settings_page_includes_form(self, client_with_mocks):
        """Should include a form for submitting settings."""
        client, _, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert "<form" in response.text
        assert 'method="post"' in response.text
        assert 'action="/admin/settings"' in response.text

    def test_settings_page_includes_hidden_inputs(self, client_with_mocks):
        """Should include hidden inputs for form data."""
        client, _, _ = client_with_mocks
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert 'type="hidden"' in response.text
        assert 'name="site_name"' in response.text
        assert 'name="model"' in response.text

    def test_settings_page_handles_no_audio_devices(self, client_with_mocks):
        """Should handle case when no audio devices are available."""
        client, _config_manager, audio_service = client_with_mocks
        audio_service.discover_input_devices.return_value = []
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert "System Default" in response.text


class TestSettingsPostRoute:
    """Tests for POST /admin/settings endpoint."""

    def test_settings_post_saves_configuration(self, client_with_mocks):
        """Should save configuration when form is submitted with only required fields."""
        client, config_manager, _ = client_with_mocks
        form_data = {
            "site_name": "Updated Site",
            "latitude": "50.0",
            "longitude": "-75.0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.8",
            "sensitivity": "1.5",
            "audio_device_index": "1",
            "sample_rate": "48000",
            "audio_channels": "1",
            "audio_overlap": "0.5",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        if response.status_code not in [302, 303]:
            print(f"Response status: {response.status_code}")
            if response.status_code == 422:
                print(f"Validation error: {response.json()}")
            else:
                print(f"Response text (first 500 chars): {response.text[:500]}")
        assert response.status_code in [302, 303]
        config_manager.save.assert_called_once()

    def test_settings_post_creates_correct_config_object(self, client_with_mocks):
        """Should create BirdNETConfig with correct values."""
        client, config_manager, _ = client_with_mocks
        form_data = {
            "site_name": "New Site",
            "latitude": "40.0",
            "longitude": "-80.0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.65",
            "sensitivity": "1.0",
            "audio_device_index": "2",
            "sample_rate": "44100",
            "audio_channels": "2",
            "audio_overlap": "1.0",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        assert response.status_code in [302, 303]
        saved_config = config_manager.save.call_args[0][0]
        assert isinstance(saved_config, BirdNETConfig)
        assert saved_config.site_name == "New Site"
        assert saved_config.latitude == 40.0
        assert saved_config.longitude == -80.0
        assert saved_config.species_confidence_threshold == 0.65
        assert saved_config.sensitivity_setting == 1.0
        assert saved_config.audio_device_index == 2

    def test_settings_post_handles_boolean_fields(self, client_with_mocks):
        """Should correctly handle boolean checkbox fields when provided."""
        client, config_manager, _ = client_with_mocks
        form_data = {
            "site_name": "Test",
            "latitude": "0",
            "longitude": "0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.5",
            "sensitivity": "1.25",
            "audio_device_index": "0",
            "sample_rate": "48000",
            "audio_channels": "1",
            "audio_overlap": "0.5",
            "enable_gps": "on",
            "enable_mqtt": "on",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        assert response.status_code in [302, 303]
        saved_config = config_manager.save.call_args[0][0]
        assert saved_config.enable_gps is True
        assert saved_config.enable_mqtt is True

    def test_settings_post_handles_webhook_urls(self, client_with_mocks):
        """Should correctly parse webhook URLs from comma-separated string."""
        client, config_manager, _ = client_with_mocks
        form_data = {
            "site_name": "Test",
            "latitude": "0",
            "longitude": "0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.5",
            "sensitivity": "1.25",
            "audio_device_index": "0",
            "sample_rate": "48000",
            "audio_channels": "1",
            "audio_overlap": "0.5",
            "webhook_urls": "http://example.com/hook1, http://example.com/hook2",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        assert response.status_code in [302, 303]
        saved_config = config_manager.save.call_args[0][0]
        assert saved_config.webhook_urls == ["http://example.com/hook1", "http://example.com/hook2"]

    def test_settings_post_redirects_to_settings(self, client_with_mocks):
        """Should redirect back to settings page after save."""
        client, _, _ = client_with_mocks
        form_data = {
            "site_name": "Test",
            "latitude": "0",
            "longitude": "0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.5",
            "sensitivity": "1.25",
            "audio_device_index": "0",
            "sample_rate": "48000",
            "audio_channels": "1",
            "audio_overlap": "0.5",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        assert response.status_code in [302, 303]
        assert response.headers["location"] == "/admin/settings"

    def test_settings_post_preserves_unsubmitted_fields(self, client_with_mocks, test_config):
        """Should preserve values for fields not included in the form submission."""
        client, config_manager, _ = client_with_mocks
        form_data = {
            "site_name": "Minimal",
            "latitude": "0",
            "longitude": "0",
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
            "species_confidence_threshold": "0.5",
            "sensitivity": "1.25",
            "audio_device_index": "0",
            "sample_rate": "48000",
            "audio_channels": "1",
            "audio_overlap": "0.5",
        }
        response = client.post("/admin/settings", data=form_data, follow_redirects=False)
        assert response.status_code in [302, 303]
        saved_config = config_manager.save.call_args[0][0]
        assert saved_config.enable_gps == test_config.enable_gps
        assert saved_config.enable_mqtt == test_config.enable_mqtt
        assert saved_config.birdweather_id == test_config.birdweather_id
        assert saved_config.webhook_urls == []
