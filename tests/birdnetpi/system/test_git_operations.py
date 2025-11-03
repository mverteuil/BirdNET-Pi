"""Tests for GitOperationsService."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.git_operations import GitOperationsService, GitRemote

# Type for subprocess.CompletedProcess mock spec
CompletedProcess = subprocess.CompletedProcess


class TestGitRemote:
    """Tests for GitRemote class."""

    def test_init(self):
        """Should initialize GitRemote."""
        remote = GitRemote("origin", "https://github.com/user/repo.git")
        assert remote.name == "origin"
        assert remote.url == "https://github.com/user/repo.git"

    def test_to_dict(self):
        """Should convert GitRemote to dict."""
        remote = GitRemote("upstream", "https://github.com/other/repo.git")
        result = remote.to_dict()

        assert result == {
            "name": "upstream",
            "url": "https://github.com/other/repo.git",
        }


class TestGitOperationsService:
    """Tests for GitOperationsService."""

    @pytest.fixture
    def git_service(self, path_resolver):
        """Create GitOperationsService instance for testing."""
        return GitOperationsService(path_resolver)

    def test_init(self, git_service, path_resolver):
        """Should initialize service."""
        assert git_service.path_resolver == path_resolver
        assert git_service.repo_path == path_resolver.app_dir

    def test_list_remotes_success(self, git_service):
        """Should list git remotes."""
        mock_output = (
            "origin\thttps://github.com/user/repo.git (fetch)\n"
            "origin\thttps://github.com/user/repo.git (push)\n"
            "upstream\thttps://github.com/original/repo.git (fetch)\n"
            "upstream\thttps://github.com/original/repo.git (push)\n"
        )

        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess, stdout=mock_output, returncode=0
            )

            remotes = git_service.list_remotes()

            assert len(remotes) == 2
            assert remotes[0].name == "origin"
            assert remotes[0].url == "https://github.com/user/repo.git"
            assert remotes[1].name == "upstream"
            assert remotes[1].url == "https://github.com/original/repo.git"

            mock_run.assert_called_once_with(["remote", "-v"])

    def test_list_remotes_empty(self, git_service):
        """Should return empty list when no remotes configured."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(spec=CompletedProcess, stdout="", returncode=0)

            remotes = git_service.list_remotes()

            assert len(remotes) == 0

    def test_get_remote_url_exists(self, git_service):
        """Should get URL for existing remote."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess, stdout="https://github.com/user/repo.git\n", returncode=0
            )

            url = git_service.get_remote_url("origin")

            assert url == "https://github.com/user/repo.git"
            mock_run.assert_called_once_with(["remote", "get-url", "origin"], check=False)

    def test_get_remote_url_not_exists(self, git_service):
        """Should return None for non-existent remote."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(spec=CompletedProcess, stdout="", returncode=128)

            url = git_service.get_remote_url("nonexistent")

            assert url is None

    def test_add_remote_success(self, git_service):
        """Should add a new git remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_get.return_value = None  # Remote doesn't exist
                mock_run.return_value = MagicMock(spec=CompletedProcess, returncode=0)

                git_service.add_remote("upstream", "https://github.com/original/repo.git")

                mock_run.assert_called_once_with(
                    ["remote", "add", "upstream", "https://github.com/original/repo.git"]
                )

    def test_add_remote_already_exists(self, git_service):
        """Should raise ValueError when adding duplicate remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            mock_get.return_value = "https://github.com/existing/repo.git"

            with pytest.raises(ValueError, match="Remote 'upstream' already exists"):
                git_service.add_remote("upstream", "https://github.com/new/repo.git")

    def test_update_remote_success(self, git_service):
        """Should update an existing remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_get.return_value = "https://github.com/old/repo.git"
                mock_run.return_value = MagicMock(spec=CompletedProcess, returncode=0)

                git_service.update_remote("origin", "https://github.com/new/repo.git")

                mock_run.assert_called_once_with(
                    ["remote", "set-url", "origin", "https://github.com/new/repo.git"]
                )

    def test_update_remote_not_exists(self, git_service):
        """Should raise ValueError when updating non-existent remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            mock_get.return_value = None

            with pytest.raises(ValueError, match="Remote 'nonexistent' does not exist"):
                git_service.update_remote("nonexistent", "https://github.com/new/repo.git")

    def test_delete_remote_success(self, git_service):
        """Should delete a git remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_get.return_value = "https://github.com/upstream/repo.git"
                mock_run.return_value = MagicMock(spec=CompletedProcess, returncode=0)

                git_service.delete_remote("upstream")

                mock_run.assert_called_once_with(["remote", "remove", "upstream"])

    def test_delete_remote_origin_protected(self, git_service):
        """Should prevent deletion of origin remote."""
        with pytest.raises(ValueError, match="Cannot delete 'origin' remote"):
            git_service.delete_remote("origin")

    def test_delete_remote_not_exists(self, git_service):
        """Should raise ValueError when deleting non-existent remote."""
        with patch.object(git_service, "get_remote_url", autospec=True) as mock_get:
            mock_get.return_value = None

            with pytest.raises(ValueError, match="Remote 'nonexistent' does not exist"):
                git_service.delete_remote("nonexistent")

    def test_fetch_remote(self, git_service):
        """Should fetch from a remote."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(spec=CompletedProcess, returncode=0)

            git_service.fetch_remote("origin")

            mock_run.assert_called_once_with(["fetch", "origin", "--tags"])

    def test_list_branches_success(self, git_service):
        """Should list branches from a remote."""
        # Use correct ls-remote --heads output format
        mock_output = (
            "abc123\trefs/heads/main\ndef456\trefs/heads/develop\nghi789\trefs/heads/feature/test\n"
        )

        with patch.object(git_service, "fetch_remote", autospec=True):
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_run.return_value = MagicMock(
                    spec=CompletedProcess, stdout=mock_output, returncode=0
                )

                branches = git_service.list_branches("origin")

                assert len(branches) == 3
                assert "main" in branches
                assert "develop" in branches
                assert "feature/test" in branches

    def test_list_branches_fetch_failure(self, git_service):
        """Should list branches even when fetch fails."""
        # Use correct ls-remote --heads output format
        mock_branches_output = "abc123\trefs/heads/main\ndef456\trefs/heads/develop\n"

        with patch.object(git_service, "fetch_remote", autospec=True) as mock_fetch:
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_fetch.side_effect = subprocess.CalledProcessError(1, "git fetch")
                mock_run.return_value = MagicMock(
                    spec=CompletedProcess, stdout=mock_branches_output, returncode=0
                )

                # Should continue with cached refs even if fetch fails
                branches = git_service.list_branches("origin")

                assert len(branches) == 2
                assert "main" in branches
                assert "develop" in branches

    def test_list_tags_success(self, git_service):
        """Should list tags."""
        mock_output = "v2.1.0\nv2.0.0\nv1.9.0\n"

        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess, stdout=mock_output, returncode=0
            )

            tags = git_service.list_tags()

            # Tags should be sorted in reverse (most recent first)
            assert tags == ["v2.1.0", "v2.0.0", "v1.9.0"]

    def test_list_tags_with_remote(self, git_service):
        """Should list tags from remote."""
        # Use correct ls-remote --tags output format
        mock_output = "abc123\trefs/tags/v2.1.0\ndef456\trefs/tags/v2.0.0\n"

        with patch.object(git_service, "fetch_remote", autospec=True):
            with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
                mock_run.return_value = MagicMock(
                    spec=CompletedProcess, stdout=mock_output, returncode=0
                )

                tags = git_service.list_tags("origin")

                assert tags == ["v2.1.0", "v2.0.0"]

    def test_list_tags_filters_assets(self, git_service):
        """Should filter out assets- prefixed tags from local tags."""
        mock_output = "v2.1.0\nassets-2024-01-01\nv2.0.0\nassets-test\nv1.9.0\n"

        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess, stdout=mock_output, returncode=0
            )

            tags = git_service.list_tags()

            # Should only include version tags, not assets- tags
            assert tags == ["v2.1.0", "v2.0.0", "v1.9.0"]
            assert "assets-2024-01-01" not in tags
            assert "assets-test" not in tags

    def test_list_tags_filters_assets_remote(self, git_service):
        """Should filter out assets- prefixed tags from remote tags."""
        mock_output = (
            "abc123\trefs/tags/v2.1.0\n"
            "def456\trefs/tags/assets-2024-01-01\n"
            "ghi789\trefs/tags/v2.0.0\n"
            "jkl012\trefs/tags/assets-models\n"
            "mno345\trefs/tags/v1.9.0\n"
            "pqr678\trefs/tags/v2.1.0^{}\n"  # Annotated tag reference (should be filtered)
        )

        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess, stdout=mock_output, returncode=0
            )

            tags = git_service.list_tags("origin")

            # Should only include version tags, not assets- tags or ^{} refs
            assert tags == ["v2.1.0", "v2.0.0", "v1.9.0"]
            assert "assets-2024-01-01" not in tags
            assert "assets-models" not in tags

    def test_list_tags_empty(self, git_service):
        """Should return empty list when no tags exist."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(spec=CompletedProcess, stdout="", returncode=0)

            tags = git_service.list_tags()

            assert tags == []

    def test_get_current_branch(self, git_service):
        """Should get current branch name."""
        with patch.object(git_service, "_run_git_command", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(spec=CompletedProcess, stdout="main\n", returncode=0)

            branch = git_service.get_current_branch()

            assert branch == "main"
            mock_run.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"])

    def test_run_git_command_timeout(self, git_service):
        """Should timeout git command after 30 seconds."""
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 30)

            with pytest.raises(subprocess.TimeoutExpired):
                git_service._run_git_command(["status"])

    def test_run_git_command_failure(self, git_service):
        """Should raise CalledProcessError on command failure."""
        with patch("subprocess.run", autospec=True) as mock_run:
            # When check=True, subprocess.run raises CalledProcessError on non-zero return
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "-C", str(git_service.repo_path), "status"],
                output="",
                stderr="fatal: not a git repository",
            )

            with pytest.raises(subprocess.CalledProcessError):
                git_service._run_git_command(["status"], check=True)

    def test_run_git_command_no_check(self, git_service):
        """Should not raise error when check=False."""
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.return_value = MagicMock(
                spec=CompletedProcess,
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )

            # Should not raise when check=False
            result = git_service._run_git_command(["status"], check=False)
            assert result.returncode == 128
