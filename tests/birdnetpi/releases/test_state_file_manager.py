"""Tests for StateFileManager class in update_manager module."""

import json
import os
from unittest.mock import MagicMock

import pytest

from birdnetpi.releases.update_manager import StateFileManager
from birdnetpi.system.file_manager import FileManager


@pytest.fixture
def mock_file_manager(tmp_path):
    """Provide a mock FileManager for testing."""
    mock_fm = MagicMock(spec=FileManager)
    mock_fm.base_path = tmp_path
    return mock_fm


@pytest.fixture
def state_file_manager(mock_file_manager, path_resolver, tmp_path):
    """Provide a StateFileManager instance for testing.

    Uses the global path_resolver fixture to prevent MagicMock file creation.
    """
    # Override the update state path to use tmp_path
    update_state_path = tmp_path / "update_state.json"
    update_lock_path = tmp_path / "update.lock"

    path_resolver.get_update_state_path = lambda: update_state_path
    path_resolver.get_update_lock_path = lambda: update_lock_path

    return StateFileManager(mock_file_manager, path_resolver)


class TestStateFileManager:
    """Test the StateFileManager class."""

    def test_initialization(self, state_file_manager, tmp_path):
        """Should initialize with correct paths."""
        assert state_file_manager.state_path == tmp_path / "update_state.json"
        assert state_file_manager.lock_path == tmp_path / "update.lock"

    def test_read_state_no_file(self, state_file_manager):
        """Should return None when state file doesn't exist."""
        result = state_file_manager.read_state()
        assert result is None

    def test_read_state_with_file(self, state_file_manager):
        """Should read and parse state from JSON file."""
        test_state = {
            "phase": "downloading",
            "progress": 50,
            "target_version": "v1.2.3",
            "updated_at": "2024-01-01T12:00:00",
        }
        state_file_manager.state_path.write_text(json.dumps(test_state))

        result = state_file_manager.read_state()
        assert result == test_state

    def test_read_state_invalid_json(self, state_file_manager):
        """Should return None on invalid JSON."""
        state_file_manager.state_path.write_text("invalid json {]")

        result = state_file_manager.read_state()
        assert result is None

    def test_write_state(self, state_file_manager):
        """Should write state to file atomically."""
        test_state = {"phase": "applying", "progress": 75, "target_version": "v1.2.3"}

        state_file_manager.write_state(test_state)

        # Read the written file
        written_data = json.loads(state_file_manager.state_path.read_text())
        assert written_data["phase"] == "applying"
        assert written_data["progress"] == 75
        assert written_data["target_version"] == "v1.2.3"
        assert "updated_at" in written_data  # Should add timestamp

    def test_write_state_atomic(self, state_file_manager, mocker):
        """Should write atomically using temp file and rename."""
        test_state = {"phase": "testing"}
        mock_rename = mocker.patch("pathlib.Path.rename", autospec=True)

        state_file_manager.write_state(test_state)

        # Should call rename for atomic operation
        mock_rename.assert_called_once()

    def test_clear_state(self, state_file_manager):
        """Should delete state file if it exists."""
        # Create a state file
        state_file_manager.state_path.write_text('{"phase": "old"}')
        assert state_file_manager.state_path.exists()

        state_file_manager.clear_state()
        assert not state_file_manager.state_path.exists()

    def test_clear_state_no_file(self, state_file_manager):
        """Should not error when clearing non-existent state."""
        assert not state_file_manager.state_path.exists()
        state_file_manager.clear_state()  # Should not raise
        assert not state_file_manager.state_path.exists()

    def test_acquire_lock_success(self, state_file_manager):
        """Should acquire lock successfully."""
        result = state_file_manager.acquire_lock()
        assert result is True
        assert state_file_manager.lock_path.exists()
        assert int(state_file_manager.lock_path.read_text().strip()) == os.getpid()

        # Clean up
        state_file_manager.release_lock()

    def test_acquire_lock_already_locked(
        self, state_file_manager, mock_file_manager, path_resolver
    ):
        """Should fail to acquire lock when already locked."""
        # First acquisition should succeed
        assert state_file_manager.acquire_lock() is True

        # Create another instance trying to acquire the same lock
        another_manager = StateFileManager(mock_file_manager, path_resolver)

        # Second acquisition should fail (current process still running)
        assert another_manager.acquire_lock() is False

        # Clean up
        state_file_manager.release_lock()

    def test_acquire_lock_with_stale_lock(self, state_file_manager):
        """Should acquire lock after removing stale lock."""
        # Write a non-existent PID to lock file
        stale_pid = 99999999
        state_file_manager.lock_path.write_text(str(stale_pid))

        # Should acquire lock (after removing stale lock)
        result = state_file_manager.acquire_lock()
        assert result is True
        assert int(state_file_manager.lock_path.read_text().strip()) == os.getpid()

        # Clean up
        state_file_manager.release_lock()

    def test_release_lock(self, state_file_manager):
        """Should release lock and delete lock file."""
        state_file_manager.acquire_lock()
        assert state_file_manager.lock_path.exists()

        state_file_manager.release_lock()
        assert not state_file_manager.lock_path.exists()

    def test_release_lock_no_lock(self, state_file_manager):
        """Should handle releasing when no lock is held."""
        state_file_manager.release_lock()  # Should not raise
        assert not state_file_manager.lock_path.exists()

    def test_acquire_lock_with_custom_pid(self, state_file_manager):
        """Should write custom PID when provided."""
        custom_pid = 12345
        result = state_file_manager.acquire_lock(pid=custom_pid)
        assert result is True
        assert int(state_file_manager.lock_path.read_text().strip()) == custom_pid

        # Clean up
        state_file_manager.release_lock()
