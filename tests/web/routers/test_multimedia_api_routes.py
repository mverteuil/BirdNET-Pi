"""Tests for multimedia API routes."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import AudioFile
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.multimedia_api_routes import router


@pytest.fixture
def mock_audio_file():
    """Create a mock audio file record."""
    return AudioFile(
        id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        file_path=Path("test_audio.wav"),  # Relative to recordings directory
        duration=3.0,
        size_bytes=48000,
    )


@pytest.fixture
def client(path_resolver, mock_audio_file, tmp_path):
    """Create test client with multimedia API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override get_recordings_dir to use temp directory
    temp_recordings_dir = tmp_path / "recordings"
    temp_recordings_dir.mkdir(parents=True, exist_ok=True)
    path_resolver.get_recordings_dir = lambda: temp_recordings_dir

    # Create the audio file on disk
    test_audio_path = temp_recordings_dir / "test_audio.wav"
    test_audio_path.write_bytes(b"RIFF" + b"\x00" * 44)  # Minimal WAV header

    # Mock the database service
    mock_core_database = MagicMock(spec=CoreDatabaseService)
    mock_session = MagicMock(spec=AsyncSession)

    # Setup async context manager
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = mock_session
    mock_session_context.__aexit__.return_value = None
    mock_core_database.get_async_db.return_value = mock_session_context

    # Mock the query result for success case
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_audio_file
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Override services
    container.core_database.override(mock_core_database)
    container.path_resolver.override(path_resolver)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.multimedia_api_routes"])

    # Include the router
    app.include_router(router, prefix="/api")

    # Create test client
    client = TestClient(app)

    # Store mocks for access in tests
    client.mock_core_database = mock_core_database  # type: ignore[attr-defined]
    client.mock_session = mock_session  # type: ignore[attr-defined]
    client.path_resolver = path_resolver  # type: ignore[attr-defined]
    client.mock_audio_file = mock_audio_file  # type: ignore[attr-defined]
    client.test_audio_path = test_audio_path  # type: ignore[attr-defined]

    yield client

    # Cleanup
    if test_audio_path.exists():
        test_audio_path.unlink()


class TestGetAudioFile:
    """Test audio file retrieval endpoint."""

    def test_get_audio_file_success(self, client):
        """Should return audio file with correct headers when file exists."""
        response = client.get("/api/audio/550e8400-e29b-41d4-a716-446655440000")

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["Accept-Ranges"] == "bytes"
        assert "max-age=3600" in response.headers["Cache-Control"]

    def test_get_audio_file_not_found_in_database(self, client):
        """Should return 404 when audio file ID not found in database."""
        # Change mock to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        client.mock_session.execute = AsyncMock(return_value=mock_result)

        response = client.get("/api/audio/550e8400-e29b-41d4-a716-446655440001")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_audio_file_not_found_on_disk(self, client):
        """Should return 404 when audio file exists in database but not on disk."""
        # Remove the audio file from disk
        if client.test_audio_path.exists():
            client.test_audio_path.unlink()

        response = client.get("/api/audio/550e8400-e29b-41d4-a716-446655440000")

        assert response.status_code == 404
        assert "not found on disk" in response.json()["detail"].lower()

    def test_get_audio_file_invalid_uuid(self, client):
        """Should return 422 validation error for invalid UUID format."""
        response = client.get("/api/audio/not-a-valid-uuid")

        assert response.status_code == 422

    def test_get_audio_file_database_error(self, client):
        """Should return 500 error when database error occurs."""
        # Simulate database error
        client.mock_session.execute = AsyncMock(side_effect=Exception("Database connection failed"))

        response = client.get("/api/audio/550e8400-e29b-41d4-a716-446655440000")

        assert response.status_code == 500
        assert "Error serving audio file" in response.json()["detail"]
