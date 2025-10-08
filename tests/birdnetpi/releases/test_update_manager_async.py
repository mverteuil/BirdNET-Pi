"""Tests for async UpdateManager methods."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from birdnetpi.config.models import BirdNETConfig, UpdateConfig
from birdnetpi.releases.update_manager import StateFileManager, UpdateManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.system_control import SystemControlService


@pytest.fixture
def mock_system_control():
    """Provide a mock SystemControlService."""
    mock = MagicMock(spec=SystemControlService)
    return mock


@pytest.fixture
def mock_file_manager(tmp_path):
    """Provide a mock FileManager."""
    mock = MagicMock(spec=FileManager, base_path=tmp_path)
    return mock


@pytest.fixture
def update_manager_with_state(path_resolver, mock_system_control, mock_file_manager, tmp_path):
    """Provide UpdateManager with StateFileManager configured.

    Uses the global path_resolver fixture to prevent MagicMock file creation.
    """
    update_state_path = tmp_path / "update_state.json"
    update_lock_path = tmp_path / "update.lock"
    rollback_dir = tmp_path / "rollback"
    rollback_dir.mkdir()
    path_resolver.get_update_state_path = lambda: update_state_path
    path_resolver.get_update_lock_path = lambda: update_lock_path
    path_resolver.get_rollback_dir = lambda: rollback_dir
    path_resolver.get_repo_path = lambda: tmp_path
    manager = UpdateManager(
        path_resolver=path_resolver,
        file_manager=mock_file_manager,
        system_control=mock_system_control,
    )
    return manager


@pytest.fixture
def mock_state_manager(update_manager_with_state):
    """Provide a mock StateFileManager."""
    mock = MagicMock(spec=StateFileManager)
    return mock


class TestUpdateManagerAsync:
    """Test async methods of UpdateManager."""

    @pytest.mark.asyncio
    async def test_check_for_updates_with_update_available(self, update_manager_with_state, mocker):
        """Should detect available updates correctly."""
        mocker.patch.object(update_manager_with_state, "get_current_version", return_value="v1.0.0")
        mocker.patch.object(update_manager_with_state, "get_latest_version", return_value="v1.1.0")
        mocker.patch.object(update_manager_with_state, "_is_newer_version", return_value=True)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {
            "body": "## New Features\n- Added update system",
            "html_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.get", autospec=True, return_value=mock_response):
            result = await update_manager_with_state.check_for_updates()
        assert result["update_available"] is True
        assert result["current_version"] == "v1.0.0"
        assert result["latest_version"] == "v1.1.0"
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_check_for_updates_when_up_to_date(self, update_manager_with_state, mocker):
        """Should report no updates when already on latest version."""
        mocker.patch.object(update_manager_with_state, "get_current_version", return_value="v1.1.0")
        mocker.patch.object(update_manager_with_state, "get_latest_version", return_value="v1.1.0")
        mocker.patch.object(update_manager_with_state, "_is_newer_version", return_value=False)
        result = await update_manager_with_state.check_for_updates()
        assert result["update_available"] is False
        assert result["current_version"] == "v1.1.0"
        assert result["latest_version"] == "v1.1.0"

    @pytest.mark.asyncio
    async def test_apply_update_success(self, update_manager_with_state, mocker):
        """Should successfully apply an update."""
        update_manager_with_state.state_manager.acquire_lock = MagicMock(
            spec=callable, return_value=True
        )
        update_manager_with_state.state_manager.write_state = MagicMock(spec=callable)
        update_manager_with_state.state_manager.release_lock = MagicMock(spec=callable)
        mocker.patch.object(
            update_manager_with_state,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": str(Path("/tmp/backup.db"))},
        )
        mocker.patch.object(
            update_manager_with_state, "_perform_git_update", new_callable=AsyncMock
        )
        mocker.patch.object(
            update_manager_with_state, "_update_dependencies", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager_with_state, "_run_migrations", new_callable=AsyncMock)
        mocker.patch.object(update_manager_with_state, "_restart_services", new_callable=AsyncMock)
        result = await update_manager_with_state.apply_update("v1.1.0")
        assert result["success"] is True
        assert result["version"] == "v1.1.0"
        update_manager_with_state.state_manager.acquire_lock.assert_called_once()
        update_manager_with_state.state_manager.release_lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_update_lock_failed(self, update_manager_with_state):
        """Should fail if cannot acquire lock."""
        update_manager_with_state.state_manager.acquire_lock = MagicMock(
            spec=callable, return_value=False
        )
        result = await update_manager_with_state.apply_update("v1.1.0")
        assert result["success"] is False
        assert "already in progress" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_apply_update_with_rollback_on_error(self, update_manager_with_state, mocker):
        """Should rollback on update failure."""
        update_manager_with_state.state_manager.acquire_lock = MagicMock(
            spec=callable, return_value=True
        )
        update_manager_with_state.state_manager.write_state = MagicMock(spec=callable)
        update_manager_with_state.state_manager.release_lock = MagicMock(spec=callable)
        rollback_info = {"commit": "abc123", "db_backup": str(Path("/tmp/backup.db"))}
        mocker.patch.object(
            update_manager_with_state,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value=rollback_info,
        )
        mocker.patch.object(
            update_manager_with_state,
            "_perform_git_update",
            new_callable=AsyncMock,
            side_effect=Exception("Git update failed"),
        )
        mock_rollback = mocker.patch.object(
            update_manager_with_state, "_perform_rollback", new_callable=AsyncMock
        )
        result = await update_manager_with_state.apply_update("v1.1.0")
        assert result["success"] is False
        assert "Git update failed" in result["error"]
        mock_rollback.assert_called_once_with(rollback_info)

    @pytest.mark.asyncio
    async def test_create_rollback_point(self, update_manager_with_state, mocker):
        """Should create a rollback point with commit and database backup."""
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_run.return_value.stdout = "abc123def"
        mock_run.return_value.returncode = 0
        mock_copy = mocker.patch("birdnetpi.releases.update_manager.shutil.copy2")
        db_path = update_manager_with_state.path_resolver.get_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()
        config_path = update_manager_with_state.path_resolver.get_birdnetpi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.touch()
        result = await update_manager_with_state._create_rollback_point()
        assert result["commit"] == "abc123def"
        assert "rollback" in result["db_backup"]
        assert mock_copy.call_count == 2

    @pytest.mark.asyncio
    async def test_perform_rollback(self, update_manager_with_state, mocker):
        """Should perform rollback to previous state."""
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_copy = mocker.patch("birdnetpi.releases.update_manager.shutil.copy2")
        rollback_dir = update_manager_with_state.path_resolver.get_rollback_dir()
        db_backup_path = rollback_dir / "birdnetpi.db"
        db_backup_path.touch()
        config_backup_path = rollback_dir / "config.yaml"
        config_backup_path.touch()
        rollback_info = {
            "commit": "abc123def",
            "config_backup": str(config_backup_path),
            "db_backup": str(db_backup_path),
            "created_at": "2024-01-01T12:00:00",
        }
        await update_manager_with_state._perform_rollback(rollback_info)
        calls = mock_run.call_args_list
        assert any("reset" in str(call) and "abc123def" in str(call) for call in calls)
        assert mock_copy.call_count == 2

    @pytest.mark.asyncio
    async def test_restart_services(self, update_manager_with_state, mock_system_control):
        """Should restart services in correct order."""
        await update_manager_with_state._restart_services()
        assert mock_system_control.restart_service.call_count > 0

    @pytest.mark.asyncio
    async def test_update_dependencies(self, update_manager_with_state, mocker):
        """Should update Python dependencies."""
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_run.return_value.returncode = 0
        await update_manager_with_state._update_dependencies()
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["uv", "sync"]
        assert mock_run.call_args.kwargs.get("cwd") == str(update_manager_with_state.app_dir)

    def test_is_newer_version_semantic(self, update_manager_with_state):
        """Should correctly compare semantic version strings."""
        assert update_manager_with_state._is_newer_version("v1.1.0", "v1.0.0") is True
        assert update_manager_with_state._is_newer_version("v1.0.0", "v1.1.0") is False
        assert update_manager_with_state._is_newer_version("v1.0.0", "v1.0.0") is False
        assert update_manager_with_state._is_newer_version("v2.0.0", "v1.9.9") is True

    @patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
    def test_get_current_version(self, mock_run, update_manager_with_state):
        """Should get current version from git."""
        mock_run.return_value.stdout = "v1.0.0\n"
        mock_run.return_value.returncode = 0
        version = update_manager_with_state.get_current_version()
        assert version == "v1.0.0"

    @patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
    def test_get_latest_version(self, mock_run, update_manager_with_state):
        """Should get latest version from remote."""
        config = BirdNETConfig(updates=UpdateConfig())
        mock_run.return_value.stdout = (
            "abc123\trefs/tags/v1.0.0\ndef456\trefs/tags/v1.1.0\nghi789\trefs/tags/v1.2.0\n"
        )
        mock_run.return_value.returncode = 0
        version = update_manager_with_state.get_latest_version(config)
        assert version == "v1.2.0"
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == [
            "git",
            "-C",
            str(update_manager_with_state.app_dir),
            "ls-remote",
            "--tags",
            "origin",
        ]
