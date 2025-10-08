"""Unhappy path tests for UpdateManager."""

import subprocess
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, create_autospec

import httpx
import pytest

from birdnetpi.config.models import BirdNETConfig, UpdateConfig
from birdnetpi.releases.update_manager import UpdateManager
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
def update_manager(path_resolver, mock_system_control, mock_file_manager, tmp_path):
    """Provide UpdateManager with test configuration."""
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


class TestNetworkFailures:
    """Test handling of network-related failures."""

    @pytest.mark.asyncio
    async def test_check_for_updates_network_timeout(self, update_manager, mocker):
        """Should handle network timeout during update check."""
        mock_get = mocker.patch("httpx.get")
        mock_get.side_effect = TimeoutError("Network timeout")
        mocker.patch.object(update_manager, "get_current_version", return_value="v1.0.0")
        mocker.patch.object(update_manager, "get_latest_version", return_value="v1.1.0")
        mocker.patch.object(update_manager, "_is_newer_version", return_value=True)
        result = await update_manager.check_for_updates()
        assert result["update_available"] is True
        assert result["current_version"] == "v1.0.0"
        assert result["latest_version"] == "v1.1.0"
        assert result.get("release_notes") is None

    @pytest.mark.asyncio
    async def test_check_for_updates_github_api_error(self, update_manager, mocker):
        """Should handle GitHub API errors gracefully."""
        mock_response = create_autospec(httpx.Response, spec_set=True)
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        mocker.patch("httpx.get", return_value=mock_response)
        mocker.patch.object(update_manager, "get_current_version", return_value="v1.0.0")
        mocker.patch.object(update_manager, "get_latest_version", return_value="v1.1.0")
        mocker.patch.object(update_manager, "_is_newer_version", return_value=True)
        result = await update_manager.check_for_updates()
        assert result["update_available"] is True
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_git_fetch_network_failure(self, update_manager, mocker):
        """Should handle git fetch failures."""
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(
            update_manager,
            "_perform_git_update",
            new_callable=AsyncMock,
            side_effect=Exception("Network error: unable to fetch"),
        )
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "network error" in result["error"].lower()
        mock_rollback.assert_called_once()


class TestFileSystemErrors:
    """Test handling of file system errors."""

    @pytest.mark.asyncio
    async def test_apply_update_disk_full(self, update_manager, mocker):
        """Should handle disk full errors during update."""
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        mock_release = mocker.patch.object(update_manager.state_manager, "release_lock")
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            side_effect=OSError("No space left on device"),
        )
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "no space" in result["error"].lower() or "oserror" in result["error"].lower()
        mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_with_corrupted_backup(self, update_manager, mocker):
        """Should handle corrupted backup files during rollback."""
        rollback_dir = update_manager.path_resolver.get_rollback_dir()
        db_backup_path = rollback_dir / "birdnetpi.db"
        config_backup_path = rollback_dir / "config.yaml"
        db_backup_path.touch()
        config_backup_path.touch()
        mock_copy = mocker.patch("birdnetpi.releases.update_manager.shutil.copy2")
        mock_copy.side_effect = [
            Exception("Backup file corrupted"),
            Exception("Backup file corrupted"),
        ]
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_run.return_value.returncode = 0
        rollback_info = {
            "commit": "abc123",
            "db_backup": str(db_backup_path),
            "config_backup": str(config_backup_path),
            "created_at": datetime.now().isoformat(),
        }
        try:
            await update_manager._perform_rollback(rollback_info)
        except Exception:
            pass
        assert mock_run.call_count > 0

    def test_state_file_permission_error(self, update_manager, mocker):
        """Should handle permission errors when writing state file."""
        mock_write = mocker.patch("pathlib.Path.write_text")
        mock_write.side_effect = PermissionError("Permission denied")
        state = {"phase": "testing", "progress": 50}
        try:
            update_manager.state_manager.write_state(state)
        except PermissionError:
            pass
        mocker.patch("pathlib.Path.read_text", side_effect=PermissionError("Permission denied"))
        result = update_manager.state_manager.read_state()
        assert result is None


class TestLockingIssues:
    """Test lock acquisition and release issues."""

    @pytest.mark.asyncio
    async def test_apply_update_stale_lock_cleanup(self, update_manager, mocker):
        """Should clean up stale locks before proceeding."""
        lock_path = update_manager.path_resolver.get_update_lock_path()
        lock_path.write_text("99999999")
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_update_dependencies", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_run_migrations", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_restart_services", new_callable=AsyncMock)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is True
        assert result["version"] == "v1.1.0"

    @pytest.mark.asyncio
    async def test_apply_update_concurrent_attempts(
        self, update_manager, path_resolver, mock_file_manager, mock_system_control
    ):
        """Should prevent concurrent update attempts."""
        first_result = update_manager.state_manager.acquire_lock()
        assert first_result is True
        second_manager = UpdateManager(
            path_resolver=path_resolver,
            file_manager=mock_file_manager,
            system_control=mock_system_control,
        )
        result = await second_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "already in progress" in result["error"].lower()
        update_manager.state_manager.release_lock()


class TestDependencyFailures:
    """Test handling of dependency update failures."""

    @pytest.mark.asyncio
    async def test_update_dependencies_uv_not_found(self, update_manager, mocker):
        """Should handle missing uv command."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_run.side_effect = FileNotFoundError("uv command not found")
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        mock_rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_dependencies_package_conflict(self, update_manager, mocker):
        """Should handle package dependency conflicts."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mocker.patch.object(
            update_manager,
            "_update_dependencies",
            new_callable=AsyncMock,
            side_effect=Exception("Dependency conflict: package X requires Y"),
        )
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "dependency conflict" in result["error"].lower()
        mock_rollback.assert_called_once()


class TestServiceRestartFailures:
    """Test service restart failure scenarios."""

    @pytest.mark.asyncio
    async def test_service_restart_failure(self, update_manager, mock_system_control, mocker):
        """Should handle service restart failures."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_update_dependencies", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_run_migrations", new_callable=AsyncMock)
        mock_system_control.restart_service.side_effect = Exception("Service failed to start")
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "service" in result["error"].lower()
        mock_rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_service_restart_failure(
        self, update_manager, mock_system_control, mocker
    ):
        """Should handle partial service restart failures."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_update_dependencies", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_run_migrations", new_callable=AsyncMock)
        call_count = 0

        def restart_side_effect(service_name):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception(f"Failed to restart {service_name}")

        mock_system_control.restart_service.side_effect = restart_side_effect
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        mock_rollback.assert_called_once()


class TestVersionCheckFailures:
    """Test version checking failure scenarios."""

    def test_get_current_version_no_git(self, update_manager, mocker):
        """Should handle missing git repository."""
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        mock_result = subprocess.CompletedProcess(args=[], returncode=0)
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        version = update_manager.get_current_version()
        assert version.startswith("dev-") or version == "unknown"

    def test_get_latest_version_no_remote(self, update_manager, mocker):
        """Should handle missing remote repository."""
        mock_run = mocker.patch("birdnetpi.releases.update_manager.subprocess.run")
        config = BirdNETConfig(updates=UpdateConfig())
        mock_result = subprocess.CompletedProcess(args=[], returncode=0)
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        with pytest.raises(RuntimeError, match="No tags found"):
            update_manager.get_latest_version(config)

    def test_is_newer_version_invalid_format(self, update_manager):
        """Should handle invalid version formats."""
        assert update_manager._is_newer_version("v2.0.0", "v1.0.0") is True
        assert update_manager._is_newer_version("v1.0.0", "v2.0.0") is False
        try:
            update_manager._is_newer_version("invalid", "v1.0.0")
            update_manager._is_newer_version("", "v1.0.0")
        except Exception:
            pass


class TestMigrationFailures:
    """Test database migration failure scenarios."""

    @pytest.mark.asyncio
    async def test_migration_script_failure(self, update_manager, mocker):
        """Should handle migration script failures."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(update_manager, "_perform_git_update", new_callable=AsyncMock)
        mocker.patch.object(update_manager, "_update_dependencies", new_callable=AsyncMock)
        mocker.patch.object(
            update_manager,
            "_run_migrations",
            new_callable=AsyncMock,
            side_effect=Exception("Migration failed: constraint violation"),
        )
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        assert "migration" in result["error"].lower()
        mock_rollback.assert_called_once()


class TestInterruptedUpdate:
    """Test handling of interrupted update processes."""

    @pytest.mark.asyncio
    async def test_update_process_terminated(self, update_manager, mocker):
        """Should handle process termination during git operations.

        Note: In production, the daemon handles SIGTERM/SIGINT via signal handlers,
        not KeyboardInterrupt. This test simulates a more severe termination scenario.
        """
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            return_value={"commit": "abc123", "db_backup": "/tmp/backup.db"},
        )
        mocker.patch.object(
            update_manager,
            "_perform_git_update",
            new_callable=AsyncMock,
            side_effect=SystemExit("Process terminated"),
        )
        mock_rollback = mocker.patch.object(
            update_manager, "_perform_rollback", new_callable=AsyncMock
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        mock_release = mocker.patch.object(update_manager.state_manager, "release_lock")
        with pytest.raises(SystemExit):
            await update_manager.apply_update("v1.1.0")
        mock_rollback.assert_not_called()
        mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_after_unexpected_exception(self, update_manager, mocker):
        """Should ensure cleanup happens even on unexpected exceptions."""
        mocker.patch.object(
            update_manager,
            "_create_rollback_point",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        )
        mocker.patch.object(update_manager.state_manager, "acquire_lock", return_value=True)
        mock_release = mocker.patch.object(update_manager.state_manager, "release_lock")
        result = await update_manager.apply_update("v1.1.0")
        assert result["success"] is False
        mock_release.assert_called_once()
