from unittest.mock import MagicMock, create_autospec, patch

import httpx
import pytest

from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.system_control import SystemControlService


@pytest.fixture
def update_manager(path_resolver, tmp_path):
    """Provide an UpdateManager instance for testing."""
    mock_file_manager = MagicMock(spec=FileManager)
    mock_system_control = MagicMock(spec=SystemControlService)
    manager = UpdateManager(
        path_resolver=path_resolver,
        file_manager=mock_file_manager,
        system_control=mock_system_control,
    )
    manager.app_dir = tmp_path
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for i in range(6):
        (scripts_dir / f"script{i}.sh").touch()
    return manager


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_update_birdnet(mock_run, update_manager, test_config):
    """Should update BirdNET successfully."""
    update_manager.update_birdnet(test_config)
    assert mock_run.call_count == 11
    update_manager.system_control.daemon_reload.assert_called_once()


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind(mock_run, update_manager, test_config):
    """Should return the number of commits behind."""
    mock_run.return_value.stdout = (
        "Your branch is behind 'origin/main' by 3 commits, and can be fast-forwarded."
    )
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 3
    mock_run.assert_any_call(
        ["git", "-C", str(update_manager.app_dir), "fetch", "origin", "main"],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "git_output,expected_commits,raises_exception",
    [
        pytest.param(
            "Your branch and 'origin/main' have diverged, "
            "and have 1 and 2 different commits each, respectively.",
            3,
            False,
            id="diverged",
        ),
        pytest.param(
            "Your branch is up to date with 'origin/main'.",
            0,
            False,
            id="up_to_date",
        ),
        pytest.param(
            None,
            -1,
            True,
            id="error",
        ),
    ],
)
@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_scenarios(
    mock_run, update_manager, test_config, git_output, expected_commits, raises_exception
):
    """Should return correct commit count based on git status."""
    if raises_exception:
        mock_run.side_effect = Exception
    else:
        mock_run.return_value.stdout = git_output
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == expected_commits


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_uses_custom_remote(mock_run, update_manager, test_config):
    """Should use custom git remote and branch from config."""
    test_config.updates.git_remote = "upstream"
    test_config.updates.git_branch = "develop"
    mock_run.return_value.stdout = "Your branch is up to date with 'upstream/develop'."
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 0
    mock_run.assert_any_call(
        ["git", "-C", str(update_manager.app_dir), "fetch", "upstream", "develop"],
        check=True,
        capture_output=True,
    )


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_latest_version_uses_custom_remote(mock_run, update_manager, test_config):
    """Should use custom git remote from config."""
    test_config.updates.git_remote = "fork"
    test_config.updates.git_branch = "feature"
    mock_run.return_value.stdout = "abc123\trefs/tags/v2.0.0\n"
    mock_run.return_value.returncode = 0
    version = update_manager.get_latest_version(test_config)
    assert version == "v2.0.0"
    mock_run.assert_called_once_with(
        ["git", "-C", str(update_manager.app_dir), "ls-remote", "--tags", "fork"],
        capture_output=True,
        text=True,
        check=True,
    )


class TestVersionResolution:
    """Test version resolution methods."""

    @patch("httpx.Client", autospec=True)
    def test_resolve_version_latest(self, mock_client_class, update_manager):
        """Should resolve 'latest' to actual release tag."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.json.return_value = {"tag_name": "v2.1.1"}
        mock_client.get.return_value = mock_response
        result = update_manager._resolve_version("latest", "owner/repo")
        assert result == "v2.1.1"
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/latest"
        )
        mock_response.raise_for_status.assert_called_once()

    def test_resolve_version_specific(self, update_manager):
        """Should return specific version as-is."""
        result = update_manager._resolve_version("v1.5.0", "owner/repo")
        assert result == "v1.5.0"

    @patch("httpx.Client", autospec=True)
    def test_resolve_latest_asset_version(self, mock_client_class, update_manager):
        """Should resolve latest asset version from releases."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.json.return_value = [
            {"tag_name": "assets-v2.1.1"},
            {"tag_name": "v2.1.1"},
            {"tag_name": "assets-v2.0.0"},
        ]
        mock_client.get.return_value = mock_response
        result = update_manager._resolve_latest_asset_version("owner/repo")
        assert result == "v2.1.1"
        mock_client.get.assert_called_once_with("https://api.github.com/repos/owner/repo/releases")

    @patch("httpx.Client", autospec=True)
    def test_resolve_latest_asset_version__no_assets(self, mock_client_class, update_manager):
        """Should raise error when no asset releases found."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.json.return_value = [{"tag_name": "v2.1.1"}, {"tag_name": "v2.0.0"}]
        mock_client.get.return_value = mock_response
        with pytest.raises(RuntimeError, match="No asset releases found"):
            update_manager._resolve_latest_asset_version("owner/repo")

    @patch("httpx.Client", autospec=True)
    def test_resolve_latest_asset_version_http_error(self, mock_client_class, update_manager):
        """Should handle HTTP errors during asset version resolution."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_client.get.side_effect = httpx.HTTPError("Network error")
        with pytest.raises(httpx.HTTPError):
            update_manager._resolve_latest_asset_version("owner/repo")


class TestAssetValidation:
    """Test asset release validation."""

    @pytest.mark.parametrize(
        "version_input,expected_tag",
        [
            pytest.param("v1.0.0", "assets-v1.0.0", id="with_v_prefix"),
            pytest.param("1.0.0", "assets-v1.0.0", id="without_v_prefix"),
        ],
    )
    @patch("httpx.Client", autospec=True)
    def test_validate_asset_release_exists(
        self, mock_client_class, update_manager, version_input, expected_tag
    ):
        """Should validate existing asset release with various version formats."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        result = update_manager._validate_asset_release(version_input, "owner/repo")
        assert result == expected_tag
        mock_client.get.assert_called_once_with(
            f"https://api.github.com/repos/owner/repo/releases/tags/{expected_tag}"
        )

    @patch("httpx.Client", autospec=True)
    @patch.object(UpdateManager, "list_available_asset_versions", autospec=True)
    def test_validate_asset_release_not_found(
        self, mock_list_versions, mock_client_class, update_manager
    ):
        """Should raise error for non-existent asset release."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        mock_list_versions.return_value = ["v2.0.0", "v1.5.0"]
        with pytest.raises(RuntimeError, match="Asset release 'assets-v1\\.0\\.0' not found"):
            update_manager._validate_asset_release("v1.0.0", "owner/repo")


class TestAssetDownload:
    """Test asset download functionality."""

    @patch("httpx.Client", autospec=True)
    def test_download__extract_assets(self, mock_client_class, update_manager):
        """Should download and extract assets successfully."""
        # Mock GitHub API response for release assets
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.status_code = 200
        # GitHub API returns a dict with "assets" key containing the list
        mock_response.json.return_value = {
            "assets": [
                {
                    "name": "models.tar.gz",
                    "browser_download_url": "https://example.com/models.tar.gz",
                },
                {
                    "name": "ioc_reference.db.gz",
                    "browser_download_url": "https://example.com/ioc.gz",
                },
            ]
        }
        mock_client.get.return_value = mock_response

        result = update_manager._download_and_extract_assets("assets-v1.0.0", "owner/repo")

        # Should return list of assets from GitHub API
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "models.tar.gz"
        assert result[1]["name"] == "ioc_reference.db.gz"
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/tags/assets-v1.0.0"
        )

    @patch("httpx.Client", autospec=True)
    def test_download__extract_assets__no_assets_found(self, mock_client_class, update_manager):
        """Should handle case when release has no assets."""
        # Mock GitHub API response with empty assets list
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.status_code = 200
        # GitHub API returns a dict with empty "assets" array
        mock_response.json.return_value = {"assets": []}
        mock_client.get.return_value = mock_response

        result = update_manager._download_and_extract_assets("assets-v1.0.0", "owner/repo")

        # Should return empty list
        assert result == []


class TestDownloadReleaseAssets:
    """Test complete asset download workflow."""

    @patch.object(UpdateManager, "_validate_asset_release", autospec=True)
    def test_download_release_assets_validation_error(self, mock_validate, update_manager):
        """Should handle asset validation errors."""
        mock_validate.side_effect = RuntimeError("Asset not found")
        with pytest.raises(RuntimeError, match="Asset not found"):
            update_manager.download_release_assets(version="v1.0.0")


class TestListVersions:
    """Test version listing functionality."""

    @pytest.mark.parametrize(
        "method_name,expected_result",
        [
            pytest.param("list_available_versions", ["v2.1.1", "v2.0.0"], id="code_versions"),
            pytest.param(
                "list_available_asset_versions", ["v2.1.1", "v2.0.0"], id="asset_versions"
            ),
        ],
    )
    @patch("httpx.Client", autospec=True)
    def test_list_available_versions(
        self, mock_client_class, update_manager, method_name, expected_result
    ):
        """Should list available release versions based on method type."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_response = create_autospec(httpx.Response, instance=True)
        mock_response.json.return_value = [
            {"tag_name": "v2.1.1"},
            {"tag_name": "assets-v2.1.1"},
            {"tag_name": "v2.0.0"},
            {"tag_name": "assets-v2.0.0"},
        ]
        mock_client.get.return_value = mock_response
        method = getattr(update_manager, method_name)
        result = method("owner/repo")
        assert result == expected_result
        mock_client.get.assert_called_once_with("https://api.github.com/repos/owner/repo/releases")

    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("list_available_versions", id="code_versions"),
            pytest.param("list_available_asset_versions", id="asset_versions"),
        ],
    )
    @patch("httpx.Client", autospec=True)
    def test_list_versions_error_handling(self, mock_client_class, update_manager, method_name):
        """Should handle errors gracefully and return empty list."""
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_client.get.side_effect = httpx.HTTPError("Network error")
        method = getattr(update_manager, method_name)
        result = method("owner/repo")
        assert result == []
