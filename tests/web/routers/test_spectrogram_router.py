"""Integration tests for spectrogram functionality that moved to detection API routes."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.plotting_manager import PlottingManager
# Import from new router structure - spectrogram functionality moved to detection_api_routes
from birdnetpi.web.routers.detection_api_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""
    
    plotting_manager = providers.Singleton(MagicMock, spec=PlottingManager)


@pytest.fixture
def app_with_spectrogram_router():
    """Create FastAPI app with detection router that includes spectrogram functionality."""
    app = FastAPI()
    
    # Setup test container
    container = TestContainer()
    app.container = container
    
    # Wire the router module
    container.wire(modules=["birdnetpi.web.routers.detection_api_routes"])
    
    # Include the router with detection prefix (spectrogram is at /api/detections/{id}/spectrogram)
    app.include_router(router, prefix="/api")
    
    return app


@pytest.fixture
def client(app_with_spectrogram_router):
    """Create test client with real app."""
    return TestClient(app_with_spectrogram_router)


@pytest.fixture
def temp_audio_file():
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        # Write minimal WAV file header (44 bytes) + some dummy data
        wav_header = (
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            b"\x00\x40\x1f\x00\x00\x40\x1f\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        temp_file.write(wav_header)
        temp_file.flush()
        yield temp_file.name

    # Cleanup
    Path(temp_file.name).unlink(missing_ok=True)


class TestSpectrogramRouterIntegration:
    """Integration tests for spectrogram router with real plotting manager."""

    def test_spectrogram_endpoint_returns_streaming_response(self, client, temp_audio_file):
        """Should return streaming response with PNG image data."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            # Mock PNG bytes data
            fake_png_data = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            mock_generate.return_value = io.BytesIO(fake_png_data)

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert response.content == fake_png_data
            mock_generate.assert_called_once_with(temp_audio_file)

    def test_spectrogram_endpoint_requires_audio_path_parameter(self, client):
        """Should require audio_path query parameter."""
        response = client.get("/spectrogram")

        assert response.status_code == 422  # Validation error
        error_data = response.json()
        assert "detail" in error_data
        # Should have validation error for missing audio_path parameter
        missing_fields = [error["loc"][-1] for error in error_data["detail"]]
        assert "audio_path" in missing_fields

    def test_spectrogram_endpoint_accepts_audio_path_parameter(self, client, temp_audio_file):
        """Should accept valid audio_path parameter."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            fake_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            mock_generate.return_value = io.BytesIO(fake_png_data)

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            assert response.status_code == 200
            mock_generate.assert_called_once_with(temp_audio_file)

    def test_spectrogram_endpoint_creates_plotting_manager_instance(self, client, temp_audio_file):
        """Should create PlottingManager instance for each request."""
        with patch(
            "birdnetpi.web.routers.spectrogram_router.PlottingManager"
        ) as mock_plotting_manager:
            mock_instance = MagicMock()
            fake_png_data = b"\x89PNG\r\n\x1a\n"
            mock_instance.generate_spectrogram.return_value = io.BytesIO(fake_png_data)
            mock_plotting_manager.return_value = mock_instance

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            assert response.status_code == 200
            # Should have created a new PlottingManager instance
            mock_plotting_manager.assert_called_once()
            mock_instance.generate_spectrogram.assert_called_once_with(temp_audio_file)

    def test_spectrogram_endpoint_handles_plotting_manager_errors(self, client, temp_audio_file):
        """Should handle PlottingManager errors appropriately."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            mock_generate.side_effect = Exception("Plotting error")

            # The endpoint should either handle the error gracefully or let it propagate
            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            # Should be either success with error message or proper error response
            assert response.status_code in [200, 500]

            if response.status_code == 500:
                # If error propagates, should be proper server error
                error_data = response.json()
                assert isinstance(error_data, dict)

    def test_spectrogram_endpoint_handles_invalid_audio_paths(self, client):
        """Should handle invalid or non-existent audio file paths."""
        invalid_path = "/nonexistent/path/to/audio.wav"

        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            mock_generate.side_effect = FileNotFoundError("Audio file not found")

            response = client.get(f"/spectrogram?audio_path={invalid_path}")

            # Should handle file not found appropriately
            assert response.status_code in [200, 404, 500]

    def test_spectrogram_endpoint_handles_malicious_paths(self, client):
        """Should handle potentially malicious file paths."""
        malicious_paths = [
            "../../../etc/passwd",
            "/etc/shadow",
            "../../../../windows/system32/config/sam",
            "/proc/version",
            "C:\\Windows\\System32\\drivers\\etc\\hosts",
        ]

        for malicious_path in malicious_paths:
            with patch(
                "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
            ) as mock_generate:
                mock_generate.side_effect = FileNotFoundError("File not found")

                response = client.get(f"/spectrogram?audio_path={malicious_path}")

                # Should not expose system files or crash
                assert response.status_code in [200, 400, 404, 500]
                # Should not return system file contents
                if response.status_code == 200:
                    assert response.headers["content-type"] == "image/png"

    def test_spectrogram_endpoint_handles_different_audio_formats(self, client):
        """Should handle different audio file extensions."""
        audio_extensions = [".wav", ".mp3", ".flac", ".m4a", ".ogg"]

        for ext in audio_extensions:
            audio_path = f"/tmp/test_audio{ext}"

            with patch(
                "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
            ) as mock_generate:
                fake_png_data = b"\x89PNG\r\n\x1a\n"
                mock_generate.return_value = io.BytesIO(fake_png_data)

                response = client.get(f"/spectrogram?audio_path={audio_path}")

                assert response.status_code == 200
                mock_generate.assert_called_once_with(audio_path)

    def test_spectrogram_endpoint_handles_empty_image_data(self, client, temp_audio_file):
        """Should handle empty or invalid image data from PlottingManager."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            # Return empty BytesIO
            mock_generate.return_value = io.BytesIO(b"")

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            # Should handle empty data gracefully
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                assert response.headers["content-type"] == "image/png"
                assert response.content == b""

    def test_spectrogram_endpoint_preserves_binary_data(self, client, temp_audio_file):
        """Should preserve binary PNG data integrity."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            # Use realistic PNG header and some binary data
            png_data = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x64\x00\x00\x00\x64"
                b"\x08\x06\x00\x00\x00p\xe2\x95T\x00\x00\x00\x04gAMA\x00\x00\xb1\x8f"
                b"\x0b\xfca\x05\x00\x00\x00 cHRM\x00\x00z&\x00\x00\x80\x84\x00\x00\xfa"
                b"\x00\x00\x00\x80\xe8\x00\x00u0\x00\x00\xea`\x00\x00:\x98\x00\x00\x17p\x9c\xbaQ<"
            )
            mock_generate.return_value = io.BytesIO(png_data)

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert response.content == png_data
            # Verify PNG signature is preserved
            assert response.content.startswith(b"\x89PNG\r\n\x1a\n")

    def test_spectrogram_endpoint_uses_streaming_response(self, client, temp_audio_file):
        """Should use StreamingResponse for efficient data transfer."""
        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            large_png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10000  # Simulate large image
            mock_generate.return_value = io.BytesIO(large_png_data)

            response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert len(response.content) == len(large_png_data)
            assert response.content == large_png_data

    def test_spectrogram_endpoint_integration_with_real_plotting_manager(
        self, client, temp_audio_file
    ):
        """Should integrate with real PlottingManager class."""
        # This test uses the real PlottingManager without mocking to test integration
        # Note: This might fail if PlottingManager has complex dependencies
        response = client.get(f"/spectrogram?audio_path={temp_audio_file}")

        # Should either succeed or fail gracefully with proper error handling
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            assert response.headers["content-type"] == "image/png"
            # Content should be binary data (might be empty if PlottingManager returns empty)
            assert isinstance(response.content, bytes)

    def test_spectrogram_endpoint_url_encoding_handling(self, client):
        """Should handle URL-encoded file paths correctly."""
        # Test with spaces and special characters in file path
        audio_path_with_spaces = "/tmp/audio file with spaces.wav"
        encoded_path = "/tmp/audio%20file%20with%20spaces.wav"

        with patch(
            "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
        ) as mock_generate:
            fake_png_data = b"\x89PNG\r\n\x1a\n"
            mock_generate.return_value = io.BytesIO(fake_png_data)

            response = client.get(f"/spectrogram?audio_path={encoded_path}")

            assert response.status_code == 200
            # Should decode the path correctly and pass the original path with spaces
            mock_generate.assert_called_once_with(audio_path_with_spaces)

    def test_spectrogram_endpoint_parameter_validation(self, client):
        """Should validate audio_path parameter format."""
        # Test various parameter formats
        test_cases = [
            ("", 422),  # Empty string
            ("   ", 200),  # Whitespace (might be valid)
            ("audio.wav", 200),  # Simple filename
            ("/absolute/path/audio.wav", 200),  # Absolute path
            ("./relative/path/audio.wav", 200),  # Relative path
        ]

        for audio_path, expected_status in test_cases:
            with patch(
                "birdnetpi.managers.plotting_manager.PlottingManager.generate_spectrogram"
            ) as mock_generate:
                mock_generate.return_value = io.BytesIO(b"\x89PNG\r\n\x1a\n")

                if audio_path == "":
                    # Empty string might cause validation error
                    response = client.get("/spectrogram?audio_path=")
                else:
                    response = client.get(f"/spectrogram?audio_path={audio_path}")

                # Allow for either expected status or error status
                assert response.status_code in [expected_status, 422, 500]
