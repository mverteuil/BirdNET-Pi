import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates

from birdnetpi.web.main import app
from birdnetpi.models.audio_device import AudioDevice
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.forms import AudioDeviceSelectionForm


@pytest.fixture(autouse=True)
def mock_app_state_for_audio_router(file_path_resolver):
    """Should set up mock application state for audio router tests."""
    # Create mock objects
    mock_config = MagicMock()
    mock_audio_device_service = MagicMock()

    # Set app.state.templates to a real Jinja2Templates instance
    app.state.templates = Jinja2Templates(directory=file_path_resolver.get_templates_dir())

    # Configure mock_config attributes
    mock_config.audio_input_device_index = 0 # Default value for testing

    # Store original app.state attributes
    original_config = app.state.config if hasattr(app.state, 'config') else None
    original_templates = app.state.templates if hasattr(app.state, 'templates') else None
    original_audio_device_service = app.state.audio_device_service if hasattr(app.state, 'audio_device_service') else None

    # Assign mock objects to app.state
    app.state.config = mock_config
    app.state.audio_device_service = mock_audio_device_service

    yield

    # Restore original app.state attributes after the test
    if original_config is not None:
        app.state.config = original_config
    else:
        del app.state.config
    if original_templates is not None:
        app.state.templates = original_templates
    else:
        del app.state.templates
    if original_audio_device_service is not None:
        app.state.audio_device_service = original_audio_device_service
    else:
        del app.state.audio_device_service


class TestAudioRouter:
    """Should test the audio router endpoints."""

    def test_select_audio_device_get(self, mock_app_state_for_audio_router):
        """Should render the audio device selection page with devices."""
        with patch('birdnetpi.services.audio_device_service.AudioDeviceService.discover_input_devices') as mock_discover_input_devices:
            mock_discover_input_devices.return_value = [
                AudioDevice(
                    name='Device 1',
                    index=0,
                    host_api_index=0,
                    max_input_channels=2,
                    max_output_channels=0,
                    default_low_input_latency=0.01,
                    default_low_output_latency=0.0,
                    default_high_input_latency=0.05,
                    default_high_output_latency=0.0,
                    default_samplerate=44100.0
                ),
                AudioDevice(
                    name='Device 2',
                    index=1,
                    host_api_index=0,
                    max_input_channels=1,
                    max_output_channels=0,
                    default_low_input_latency=0.01,
                    default_low_output_latency=0.0,
                    default_high_input_latency=0.05,
                    default_high_output_latency=0.0,
                    default_samplerate=48000.0
                )
            ]

            client = TestClient(app)
            response = client.get("/audio/select_device")

            assert response.status_code == 200
            assert "Audio Device Selection" in response.text
            assert "Device 1" in response.text
            assert "Device 2" in response.text

    @pytest.mark.asyncio
    async def test_select_audio_device_post(self, mock_app_state_for_audio_router):
        """Should handle audio device selection form submission."""
        with patch('birdnetpi.services.audio_device_service.AudioDeviceService.discover_input_devices') as mock_discover_input_devices:
            mock_discover_input_devices.return_value = [
                AudioDevice(
                    name='Device 1',
                    index=0,
                    host_api_index=0,
                    max_input_channels=2,
                    max_output_channels=0,
                    default_low_input_latency=0.01,
                    default_low_output_latency=0.0,
                    default_high_input_latency=0.05,
                    default_high_output_latency=0.0,
                    default_samplerate=44100.0
                )
            ]

            client = TestClient(app)
            response = client.post("/audio/select_device", data={'device': '0', 'submit': 'Save'}, follow_redirects=False)

            assert response.status_code == 303  # Redirect after successful POST
            assert response.headers['location'] == "/audio/select_device"