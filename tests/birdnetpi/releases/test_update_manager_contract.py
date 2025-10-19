"""Test UpdateManager output matches UpdateStatusResponse contract."""

import subprocess
from unittest.mock import create_autospec, patch

import pytest

from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.web.models.update import UpdateStatusResponse


class TestUpdateManagerContract:
    """Test that UpdateManager.check_for_updates() output matches API contract."""

    @pytest.fixture
    def update_manager(self, path_resolver):
        """Create UpdateManager instance."""
        return UpdateManager(path_resolver)

    @pytest.mark.asyncio
    async def test_check_for_updates_matches_api_contract_success(self, update_manager):
        """Should deserialize UpdateManager result into UpdateStatusResponse."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # Mock development version
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 1

            mock_rev_parse = create_autospec(subprocess.CompletedProcess)
            mock_rev_parse.returncode = 0
            mock_rev_parse.stdout = "abc1234\n"

            mock_ls_remote = create_autospec(subprocess.CompletedProcess)
            mock_ls_remote.returncode = 0
            mock_ls_remote.stdout = "abc123\trefs/tags/v1.0.0\n"

            mock_run.side_effect = [mock_describe, mock_rev_parse, mock_ls_remote]

            result = await update_manager.check_for_updates()

            # This will raise ValidationError if contract doesn't match
            response = UpdateStatusResponse(**result)

            # Verify required fields are present and correct type
            assert isinstance(response.available, bool)
            assert isinstance(response.current_version, str)
            assert response.deployment_type is not None

    @pytest.mark.asyncio
    async def test_check_for_updates_matches_api_contract_error(self, update_manager):
        """Should deserialize UpdateManager error result into UpdateStatusResponse."""
        with patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True) as mock_run:
            # Mock version detection
            mock_describe = create_autospec(subprocess.CompletedProcess)
            mock_describe.returncode = 1

            mock_rev_parse = create_autospec(subprocess.CompletedProcess)
            mock_rev_parse.returncode = 0
            mock_rev_parse.stdout = "abc1234\n"

            # Mock ls-remote failure
            mock_ls_remote = create_autospec(subprocess.CompletedProcess)
            mock_ls_remote.returncode = 1
            mock_ls_remote.check_returncode = lambda: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, "git")
            )

            mock_run.side_effect = [
                mock_describe,
                mock_rev_parse,
                subprocess.CalledProcessError(1, "git"),
            ]

            result = await update_manager.check_for_updates()

            # Error response should still validate
            response = UpdateStatusResponse(**result)

            assert response.available is False
            assert response.error is not None
