"""End-to-end tests for settings functionality including UI interaction simulation."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from birdnetpi.audio.devices import AudioDevice, AudioDeviceService
from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.system.path_resolver import PathResolver


class TestSettingsE2E:
    """End-to-end tests for complete settings workflow."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for E2E testing."""
        temp_dir = tempfile.mkdtemp(prefix="e2e_settings_")
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir(exist_ok=True)

        # Save original env
        old_env = os.environ.get("BIRDNETPI_DATA")
        os.environ["BIRDNETPI_DATA"] = temp_dir

        yield temp_dir

        # Restore env
        if old_env:
            os.environ["BIRDNETPI_DATA"] = old_env
        else:
            os.environ.pop("BIRDNETPI_DATA", None)

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_audio_devices(self):
        """Mock audio devices for testing."""
        return [
            AudioDevice(
                name="USB Microphone",
                index=2,
                host_api_index=0,
                max_input_channels=1,
                max_output_channels=0,
                default_low_input_latency=0.01,
                default_low_output_latency=0.0,
                default_high_input_latency=0.04,
                default_high_output_latency=0.0,
                default_samplerate=48000.0,
            ),
            AudioDevice(
                name="Webcam Mic",
                index=3,
                host_api_index=0,
                max_input_channels=2,
                max_output_channels=0,
                default_low_input_latency=0.02,
                default_low_output_latency=0.0,
                default_high_input_latency=0.08,
                default_high_output_latency=0.0,
                default_samplerate=44100.0,
            ),
        ]

    @pytest.fixture
    def e2e_app(self, temp_data_dir, mock_audio_devices, repo_root):
        """Create app with real components for E2E testing."""
        from dependency_injector import providers
        from fastapi.templating import Jinja2Templates

        from birdnetpi.web.core.container import Container
        from birdnetpi.web.core.factory import create_app

        # Use real PathResolver with temp directory
        path_resolver = PathResolver()
        # Create test config path
        config_file = Path(temp_data_dir) / "config" / "birdnetpi.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        # Override paths to point to actual locations
        path_resolver.get_birdnetpi_config_path = lambda: config_file
        path_resolver.get_static_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "static"
        path_resolver.get_templates_dir = (
            lambda: repo_root / "src" / "birdnetpi" / "web" / "templates"
        )

        # Override container providers FIRST before creating config
        Container.path_resolver.override(providers.Singleton(lambda: path_resolver))

        # Now create initial config file using the same path_resolver
        config_manager = ConfigManager(path_resolver)
        initial_config = BirdNETConfig(
            site_name="E2E Test Site",
            latitude=63.4591,
            longitude=-19.3647,
            sensitivity_setting=1.0,
            species_confidence_threshold=0.5,
            audio_device_index=-1,
        )
        config_manager.save(initial_config)

        # Mock AudioDeviceService
        mock_audio_service = MagicMock(spec=AudioDeviceService)
        mock_audio_service.discover_input_devices.return_value = mock_audio_devices

        # Use real templates
        templates_dir = repo_root / "src" / "birdnetpi" / "web" / "templates"
        Container.templates.override(
            providers.Singleton(lambda: Jinja2Templates(directory=str(templates_dir)))
        )

        # Patch AudioDeviceService at import
        with (
            patch(
                "birdnetpi.web.routers.admin_view_routes.AudioDeviceService",
                return_value=mock_audio_service,
            ),
            patch(
                "birdnetpi.web.routers.sqladmin_view_routes.setup_sqladmin",
                side_effect=lambda app: MagicMock(),
            ),
        ):
            app = create_app()

        yield app, path_resolver, mock_audio_service

        # Cleanup overrides
        Container.path_resolver.reset_override()
        Container.templates.reset_override()

    def test_e2e_settings_page_loads_with_current_config(self, e2e_app):
        """Test that settings page loads and displays current configuration."""
        app, path_resolver, _ = e2e_app

        with TestClient(app) as client:
            # GET settings page
            response = client.get("/admin/settings")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check that current config values are displayed
            assert "E2E Test Site" in response.text
            assert "63.4591" in response.text  # latitude
            assert (
                "-19.364" in response.text or "-19.3647" in response.text
            )  # longitude (may be formatted)

            # Audio devices may not be rendered in E2E test since AudioDeviceService is mocked
            # Just check that the page has audio device select element
            assert 'name="audio_device_index"' in response.text

            # Check form is present
            assert "<form" in response.text
            assert 'action="/admin/settings"' in response.text
            assert 'method="post"' in response.text

    def test_e2e_settings_form_submission_saves_changes(self, e2e_app, temp_data_dir):
        """Test that submitting the settings form saves changes to config file."""
        app, path_resolver, _ = e2e_app

        with TestClient(app) as client:
            # Submit form with changed values
            form_data = {
                "site_name": "Updated E2E Site",
                "latitude": "51.5074",
                "longitude": "-0.1278",
                "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
                "species_confidence_threshold": "0.75",
                "sensitivity": "1.5",
                "week": "-1",
                "audio_format": "wav",
                "extraction_length": "3.0",
                "audio_device_index": "2",  # Select USB Microphone
                "sample_rate": "48000",
                "audio_channels": "1",
                "analysis_overlap": "0.5",
                "enable_gps": "on",  # Enable GPS
                "birdweather_id": "test123",
            }

            response = client.post("/admin/settings", data=form_data, follow_redirects=False)

            # Should redirect after save
            assert response.status_code in [302, 303]
            assert response.headers["location"] == "/admin/settings"

            # Verify changes were saved to file
            config_file = path_resolver.get_birdnetpi_config_path()
            assert config_file.exists()

            with open(config_file) as f:
                saved_data = yaml.safe_load(f)

            assert saved_data["site_name"] == "Updated E2E Site"
            assert saved_data["latitude"] == 51.5074
            assert saved_data["longitude"] == -0.1278
            assert saved_data["species_confidence_threshold"] == 0.75
            assert saved_data["sensitivity_setting"] == 1.5
            assert saved_data["audio_device_index"] == 2
            assert saved_data["enable_gps"] is True
            assert saved_data["birdweather_id"] == "test123"

    def test_e2e_settings_roundtrip(self, e2e_app):
        """Test complete roundtrip: load, modify, save, reload."""
        app, path_resolver, _ = e2e_app

        with TestClient(app) as client:
            # Step 1: Load initial settings page
            response1 = client.get("/admin/settings")
            assert response1.status_code == 200
            assert "E2E Test Site" in response1.text

            # Step 2: Submit changes
            form_data = {
                "site_name": "Roundtrip Test",
                "latitude": "35.6762",
                "longitude": "139.6503",
                "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
                "species_confidence_threshold": "0.85",
                "sensitivity": "2.0",
                "week": "-1",
                "audio_format": "wav",
                "extraction_length": "3.0",
                "audio_device_index": "3",  # Select Webcam Mic
                "sample_rate": "44100",
                "audio_channels": "2",
                "analysis_overlap": "1.5",
                "webhook_urls": "http://hook1.example.com, http://hook2.example.com",
            }

            response2 = client.post("/admin/settings", data=form_data, follow_redirects=True)

            # Step 3: Verify redirect happened and new page loads
            assert response2.status_code == 200
            assert "Roundtrip Test" in response2.text
            assert "35.6762" in response2.text
            assert "139.6503" in response2.text

            # Step 4: Load settings page again to verify persistence
            response3 = client.get("/admin/settings")
            assert response3.status_code == 200
            assert "Roundtrip Test" in response3.text
            assert "35.6762" in response3.text
            assert "139.6503" in response3.text

    def test_e2e_settings_validation_errors(self, e2e_app):
        """Test that invalid form data is handled properly."""
        app, _, _ = e2e_app

        with TestClient(app) as client:
            # Try to submit with missing required fields
            form_data = {
                "site_name": "",  # Empty required field
                "latitude": "invalid",  # Invalid float
                "longitude": "also_invalid",  # Invalid float
                # Missing other required fields
            }

            # This should either validate client-side (JavaScript) or server-side
            # For now, we'll test that it doesn't crash
            try:
                response = client.post("/admin/settings", data=form_data, follow_redirects=False)
                # Should get an error response or redirect with error
                assert response.status_code in [302, 303, 400, 422]
            except Exception as e:
                # Form validation might raise an exception
                assert "ValidationError" in str(type(e).__name__) or "ValueError" in str(e)

    def test_e2e_settings_handles_concurrent_access(self, e2e_app):
        """Test that settings can handle concurrent access (simulated)."""
        app, path_resolver, _ = e2e_app

        with TestClient(app) as client:
            # Simulate two users accessing settings simultaneously

            # User 1 loads the page
            response1 = client.get("/admin/settings")
            assert response1.status_code == 200

            # User 2 loads the page
            response2 = client.get("/admin/settings")
            assert response2.status_code == 200

            # User 1 submits changes
            form_data1 = {
                "site_name": "User 1 Site",
                "latitude": "10.0",
                "longitude": "20.0",
                "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
                "species_confidence_threshold": "0.6",
                "sensitivity": "1.1",
                "week": "-1",
                "audio_format": "wav",
                "extraction_length": "3.0",
                "audio_device_index": "0",
                "sample_rate": "48000",
                "audio_channels": "1",
                "analysis_overlap": "0.5",
            }

            response3 = client.post("/admin/settings", data=form_data1, follow_redirects=False)
            assert response3.status_code in [302, 303]

            # User 2 submits changes (last write wins)
            form_data2 = {
                "site_name": "User 2 Site",
                "latitude": "30.0",
                "longitude": "40.0",
                "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
                "species_confidence_threshold": "0.7",
                "sensitivity": "1.2",
                "week": "-1",
                "audio_format": "wav",
                "extraction_length": "3.0",
                "audio_device_index": "1",
                "sample_rate": "48000",
                "audio_channels": "1",
                "analysis_overlap": "0.5",
            }

            response4 = client.post("/admin/settings", data=form_data2, follow_redirects=False)
            assert response4.status_code in [302, 303]

            # Verify last write wins
            config_manager = ConfigManager(path_resolver)
            final_config = config_manager.load()
            assert final_config.site_name == "User 2 Site"
            assert final_config.latitude == 30.0

    def test_e2e_settings_preserves_unmodified_fields(self, e2e_app):
        """Test that fields not in the form are preserved during save."""
        app, path_resolver, _ = e2e_app

        # Add some extra config that's not in the form
        config_manager = ConfigManager(path_resolver)
        config = config_manager.load()
        config.git_branch = "custom-branch"
        config.git_remote = "custom-remote"
        config_manager.save(config)

        with TestClient(app) as client:
            # Submit form (without git fields)
            form_data = {
                "site_name": "Preserve Test",
                "latitude": "0.0",
                "longitude": "0.0",
                "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
                "species_confidence_threshold": "0.5",
                "sensitivity": "1.25",
                "week": "-1",
                "audio_format": "wav",
                "extraction_length": "3.0",
                "audio_device_index": "-1",
                "sample_rate": "48000",
                "audio_channels": "1",
                "analysis_overlap": "0.5",
            }

            response = client.post("/admin/settings", data=form_data, follow_redirects=False)
            assert response.status_code in [302, 303]

            # Verify git fields were preserved
            final_config = config_manager.load()
            assert final_config.git_branch == "custom-branch"
            assert final_config.git_remote == "custom-remote"
            assert final_config.site_name == "Preserve Test"
