"""Test version type detection in UpdateManager."""

import subprocess
from unittest.mock import create_autospec, patch

import pytest

from birdnetpi.releases.update_manager import UpdateManager


class TestVersionTypeDetection:
    """Test version type detection for development warning."""

    @pytest.fixture
    def update_manager(self, path_resolver):
        """Create UpdateManager instance."""
        return UpdateManager(path_resolver)

    @pytest.mark.asyncio
    async def test_development_version_sets_type(self, update_manager):
        """Should set version_type to 'development' for dev versions."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # Mock git describe to fail (not on a tag)
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 1  # Not on a tag

            # Mock git rev-parse to return commit hash
            mock_rev_parse = create_autospec(subprocess.CompletedProcess)
            mock_rev_parse.returncode = 0
            mock_rev_parse.stdout = "abc1234\n"

            # Mock git ls-remote for latest version
            mock_ls_remote = create_autospec(subprocess.CompletedProcess)
            mock_ls_remote.returncode = 0
            mock_ls_remote.stdout = "abc123\trefs/tags/v1.0.0\n"

            mock_run.side_effect = [mock_describe, mock_rev_parse, mock_ls_remote]

            result = await update_manager.check_for_updates()

            assert result["current_version"] == "dev-abc1234"
            assert result["version_type"] == "development"
            assert "latest_version" in result
            assert "update_available" in result

    @pytest.mark.asyncio
    async def test_release_version_sets_type(self, update_manager):
        """Should set version_type to 'release' for tagged versions."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # Mock git describe to succeed (on a tag)
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 0
            mock_describe.stdout = "v0.9.0\n"

            # Mock git ls-remote for latest version
            mock_ls_remote = create_autospec(subprocess.CompletedProcess)
            mock_ls_remote.returncode = 0
            mock_ls_remote.stdout = "abc123\trefs/tags/v1.0.0\n"

            mock_run.side_effect = [mock_describe, mock_ls_remote]

            result = await update_manager.check_for_updates()

            assert result["current_version"] == "v0.9.0"
            assert result["version_type"] == "release"
            assert result["latest_version"] == "v1.0.0"
            assert result["update_available"] is True

    def test_get_current_version_development(self, update_manager):
        """Should return dev- prefixed version when not on a tag."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # First call: git describe fails (not on tag)
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 1

            # Second call: git rev-parse succeeds
            mock_rev_parse = create_autospec(subprocess.CompletedProcess)
            mock_rev_parse.returncode = 0
            mock_rev_parse.stdout = "deadbeef\n"

            mock_run.side_effect = [mock_describe, mock_rev_parse]

            version = update_manager.get_current_version()

            assert version == "dev-deadbeef"

    def test_get_current_version_release(self, update_manager):
        """Should return tag version when on a tagged release."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # git describe succeeds (on a tag)
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 0
            mock_describe.stdout = "v1.2.3\n"

            mock_run.return_value = mock_describe

            version = update_manager.get_current_version()

            assert version == "v1.2.3"

    @pytest.mark.asyncio
    async def test_check_for_updates_includes_all_fields(self, update_manager):
        """Should include all required fields in update check result."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # Mock development version
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 1

            mock_rev_parse = create_autospec(subprocess.CompletedProcess)
            mock_rev_parse.returncode = 0
            mock_rev_parse.stdout = "main1234\n"

            mock_ls_remote = create_autospec(subprocess.CompletedProcess)
            mock_ls_remote.returncode = 0
            mock_ls_remote.stdout = "abc123\trefs/tags/v1.0.0\n"

            mock_run.side_effect = [mock_describe, mock_rev_parse, mock_ls_remote]

            result = await update_manager.check_for_updates()

            # Should have all required fields
            assert "current_version" in result
            assert "latest_version" in result
            assert "update_available" in result
            assert "version_type" in result
            assert "checked_at" in result

            # Version type should be correctly set
            assert result["version_type"] == "development"
