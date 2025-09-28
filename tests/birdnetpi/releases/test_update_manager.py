from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest

from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.system_control import SystemControlService


@pytest.fixture
def update_manager(path_resolver, tmp_path):
    """Provide an UpdateManager instance for testing."""
    # The global path_resolver already provides real paths for models and IOC database
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
    # Create dummy script files for testing the symlink loop
    for i in range(6):
        (scripts_dir / f"script{i}.sh").touch()
    return manager


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_update_birdnet(mock_run, update_manager, test_config):
    """Should update BirdNET successfully."""
    update_manager.update_birdnet(test_config)
    # 11 subprocess calls (removed systemctl daemon-reload)
    assert mock_run.call_count == 11
    # Verify daemon_reload was called on system_control service
    update_manager.system_control.daemon_reload.assert_called_once()


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind(mock_run, update_manager, test_config):
    """Should return the number of commits behind."""
    mock_run.return_value.stdout = (
        "Your branch is behind 'origin/main' by 3 commits, and can be fast-forwarded."
    )
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 3

    # Verify fetch was called with correct remote and branch
    mock_run.assert_any_call(
        ["git", "-C", str(update_manager.app_dir), "fetch", "origin", "main"],
        check=True,
        capture_output=True,
    )


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_diverged(mock_run, update_manager, test_config):
    """Should return the number of commits behind when diverged."""
    mock_run.return_value.stdout = (
        "Your branch and 'origin/main' have diverged, and have 1 and 2 different "
        "commits each, respectively."
    )
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 3


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_up_to_date(mock_run, update_manager, test_config):
    """Should return 0 when the branch is up to date."""
    mock_run.return_value.stdout = "Your branch is up to date with 'origin/main'."
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 0


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_error(mock_run, update_manager, test_config):
    """Should return -1 when there is an error."""
    mock_run.side_effect = Exception
    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == -1


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_commits_behind_uses_custom_remote(mock_run, update_manager, test_config):
    """Should use custom git remote and branch from config."""
    # Override the default git settings
    test_config.updates.git_remote = "upstream"
    test_config.updates.git_branch = "develop"
    mock_run.return_value.stdout = "Your branch is up to date with 'upstream/develop'."

    commits_behind = update_manager.get_commits_behind(test_config)
    assert commits_behind == 0

    # Verify fetch was called with custom remote and branch
    mock_run.assert_any_call(
        ["git", "-C", str(update_manager.app_dir), "fetch", "upstream", "develop"],
        check=True,
        capture_output=True,
    )


@patch("birdnetpi.releases.update_manager.subprocess.run", autospec=True)
def test_get_latest_version_uses_custom_remote(mock_run, update_manager, test_config):
    """Should use custom git remote from config."""
    # Override the default git settings
    test_config.updates.git_remote = "fork"
    test_config.updates.git_branch = "feature"

    mock_run.return_value.stdout = "abc123\trefs/tags/v2.0.0\n"
    mock_run.return_value.returncode = 0

    version = update_manager.get_latest_version(test_config)
    assert version == "v2.0.0"

    # Verify ls-remote was called with custom remote
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
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
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
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"tag_name": "assets-v2.1.1"},
            {"tag_name": "v2.1.1"},
            {"tag_name": "assets-v2.0.0"},
        ]
        mock_client.get.return_value = mock_response

        result = update_manager._resolve_latest_asset_version("owner/repo")

        assert result == "v2.1.1"  # Should remove 'assets-' prefix
        mock_client.get.assert_called_once_with("https://api.github.com/repos/owner/repo/releases")

    @patch("httpx.Client", autospec=True)
    def test_resolve_latest_asset_version__no_assets(self, mock_client_class, update_manager):
        """Should raise error when no asset releases found."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"tag_name": "v2.1.1"},
            {"tag_name": "v2.0.0"},
        ]
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError, match="No asset releases found"):
            update_manager._resolve_latest_asset_version("owner/repo")

    @patch("httpx.Client", autospec=True)
    def test_resolve_latest_asset_version_http_error(self, mock_client_class, update_manager):
        """Should handle HTTP errors during asset version resolution."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_client.get.side_effect = httpx.HTTPError("Network error")

        with pytest.raises(httpx.HTTPError):
            update_manager._resolve_latest_asset_version("owner/repo")


class TestAssetValidation:
    """Test asset release validation."""

    @patch("httpx.Client", autospec=True)
    def test_validate_asset_release_exists(self, mock_client_class, update_manager):
        """Should validate existing asset release."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = update_manager._validate_asset_release("v1.0.0", "owner/repo")

        assert result == "assets-v1.0.0"
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/tags/assets-v1.0.0"
        )

    @patch("httpx.Client", autospec=True)
    def test_validate_asset_release__v_prefix(self, mock_client_class, update_manager):
        """Should handle version with 'v' prefix correctly."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = update_manager._validate_asset_release("v1.0.0", "owner/repo")

        assert result == "assets-v1.0.0"

    @patch("httpx.Client", autospec=True)
    def test_validate_asset_release_without_v_prefix(self, mock_client_class, update_manager):
        """Should handle version without 'v' prefix correctly."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = update_manager._validate_asset_release("1.0.0", "owner/repo")

        assert result == "assets-v1.0.0"

    @patch("httpx.Client", autospec=True)
    @patch.object(UpdateManager, "list_available_asset_versions")
    def test_validate_asset_release_not_found(
        self, mock_list_versions, mock_client_class, update_manager
    ):
        """Should raise error for non-existent asset release."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        mock_list_versions.return_value = ["v2.0.0", "v1.5.0"]

        with pytest.raises(RuntimeError, match=r"Asset release 'assets-v1\.0\.0' not found"):
            update_manager._validate_asset_release("v1.0.0", "owner/repo")


class TestAssetDownload:
    """Test asset download functionality."""

    @patch("tempfile.mkdtemp")
    @patch("shutil.unpack_archive")
    @patch("httpx.Client", autospec=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_download__extract_assets(
        self, mock_file, mock_client_class, mock_unpack, mock_mkdtemp, update_manager, tmp_path
    ):
        """Should download and extract assets successfully."""
        # Setup temp directory
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        mock_mkdtemp.return_value = str(temp_dir)

        # Setup extracted directory
        extracted_dir = temp_dir / "extracted" / "repo-assets-v1.0.0"
        extracted_dir.mkdir(parents=True)

        # Setup HTTP client mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.headers = {"content-length": "1024"}
        mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]
        mock_client.stream.return_value.__enter__.return_value = mock_response

        result = update_manager._download_and_extract_assets("assets-v1.0.0", "owner/repo")

        assert result == extracted_dir
        mock_client.stream.assert_called_once_with(
            "GET", "https://github.com/owner/repo/archive/assets-v1.0.0.tar.gz"
        )
        mock_unpack.assert_called_once()

    @patch("tempfile.mkdtemp")
    @patch("shutil.unpack_archive")
    @patch("httpx.Client", autospec=True)
    def test_download__extract_assets__no_extracted_dir(
        self, mock_client_class, mock_unpack, mock_mkdtemp, update_manager, tmp_path
    ):
        """Should raise error when no extracted directory found."""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        mock_mkdtemp.return_value = str(temp_dir)

        # Create empty extracted directory
        extracted_dir = temp_dir / "extracted"
        extracted_dir.mkdir()

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.headers = {"content-length": "1024"}
        mock_response.iter_bytes.return_value = [b"data"]
        mock_client.stream.return_value.__enter__.return_value = mock_response

        with pytest.raises(RuntimeError, match="No extracted directory found"):
            update_manager._download_and_extract_assets("assets-v1.0.0", "owner/repo")


class TestDownloadReleaseAssets:
    """Test complete asset download workflow."""

    @patch.object(UpdateManager, "_download_and_extract_assets")
    @patch.object(UpdateManager, "_validate_asset_release")
    @patch.object(UpdateManager, "_resolve_latest_asset_version")
    @patch("shutil.copy2")
    def test_download_release_assets(
        self,
        mock_copy,
        mock_resolve_latest,
        mock_validate,
        mock_download_extract,
        update_manager,
        tmp_path,
    ):
        """Should download release assets successfully."""
        # Setup mocks - use the update_manager's path_resolver
        update_manager.path_resolver.get_models_dir.return_value = tmp_path / "models"
        update_manager.path_resolver.get_ioc_database_path.return_value = tmp_path / "ioc.db"

        mock_resolve_latest.return_value = "v1.0.0"
        mock_validate.return_value = "assets-v1.0.0"

        # Setup extracted assets
        asset_dir = tmp_path / "assets"
        asset_dir.mkdir()
        models_dir = asset_dir / "data" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "model1.tflite").write_text("model1")
        (models_dir / "model2.tflite").write_text("model2")

        db_dir = asset_dir / "data" / "database"
        db_dir.mkdir(parents=True)
        (db_dir / "ioc_reference.db").write_text("database")

        mock_download_extract.return_value = asset_dir

        # Execute
        result = update_manager.download_release_assets(
            version="latest", include_models=True, include_ioc_db=True, github_repo="owner/repo"
        )

        # Verify
        assert result["version"] == "v1.0.0"
        assert len(result["downloaded_assets"]) == 3  # 2 models + 1 database
        assert len(result["errors"]) == 0

        mock_resolve_latest.assert_called_once_with("owner/repo")
        mock_validate.assert_called_once_with("v1.0.0", "owner/repo")
        mock_download_extract.assert_called_once_with("assets-v1.0.0", "owner/repo")

    @patch.object(UpdateManager, "_download_and_extract_assets")
    @patch.object(UpdateManager, "_validate_asset_release")
    def test_download_release_assets_models_only(
        self,
        mock_validate,
        mock_download_extract,
        update_manager,
        tmp_path,
    ):
        """Should download only models when specified."""
        # Setup mocks - use the update_manager's path_resolver
        update_manager.path_resolver.get_models_dir.return_value = tmp_path / "models"

        mock_validate.return_value = "assets-v1.0.0"

        asset_dir = tmp_path / "assets"
        asset_dir.mkdir()
        models_dir = asset_dir / "data" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "model1.tflite").write_text("model1")

        mock_download_extract.return_value = asset_dir

        result = update_manager.download_release_assets(
            version="v1.0.0", include_models=True, include_ioc_db=False, github_repo="owner/repo"
        )

        assert len(result["downloaded_assets"]) == 1
        assert "Model: model1.tflite" in result["downloaded_assets"]

    @patch.object(UpdateManager, "_download_and_extract_assets")
    @patch.object(UpdateManager, "_validate_asset_release")
    def test_download_release_assets__missing_models(
        self,
        mock_validate,
        mock_download_extract,
        update_manager,
        tmp_path,
    ):
        """Should handle missing models directory gracefully."""
        # Setup mocks - use the update_manager's path_resolver
        update_manager.path_resolver.get_models_dir.return_value = tmp_path / "models"

        mock_validate.return_value = "assets-v1.0.0"

        asset_dir = tmp_path / "assets"
        asset_dir.mkdir()
        # No models directory created

        mock_download_extract.return_value = asset_dir

        result = update_manager.download_release_assets(
            version="v1.0.0", include_models=True, include_ioc_db=False, github_repo="owner/repo"
        )

        assert len(result["downloaded_assets"]) == 0
        assert "Models directory not found in release" in result["errors"]

    @patch.object(UpdateManager, "_validate_asset_release")
    def test_download_release_assets_validation_error(self, mock_validate, update_manager):
        """Should handle asset validation errors."""
        mock_validate.side_effect = RuntimeError("Asset not found")

        with pytest.raises(RuntimeError, match="Asset not found"):
            update_manager.download_release_assets(version="v1.0.0")


class TestListVersions:
    """Test version listing functionality."""

    @patch("httpx.Client", autospec=True)
    def test_list_available_versions(self, mock_client_class, update_manager):
        """Should list available code release versions."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"tag_name": "v2.1.1"},
            {"tag_name": "assets-v2.1.1"},  # Should be filtered out
            {"tag_name": "v2.0.0"},
            {"tag_name": "assets-v2.0.0"},  # Should be filtered out
        ]
        mock_client.get.return_value = mock_response

        result = update_manager.list_available_versions("owner/repo")

        assert result == ["v2.1.1", "v2.0.0"]
        mock_client.get.assert_called_once_with("https://api.github.com/repos/owner/repo/releases")

    @patch("httpx.Client", autospec=True)
    def test_list_available_asset_versions(self, mock_client_class, update_manager):
        """Should list available asset release versions."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"tag_name": "v2.1.1"},  # Should be filtered out
            {"tag_name": "assets-v2.1.1"},
            {"tag_name": "v2.0.0"},  # Should be filtered out
            {"tag_name": "assets-v2.0.0"},
        ]
        mock_client.get.return_value = mock_response

        result = update_manager.list_available_asset_versions("owner/repo")

        assert result == ["v2.1.1", "v2.0.0"]  # 'assets-' prefix removed
        mock_client.get.assert_called_once_with("https://api.github.com/repos/owner/repo/releases")

    @patch("httpx.Client", autospec=True)
    def test_list_available_versions_error(self, mock_client_class, update_manager):
        """Should handle errors gracefully and return empty list."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_client.get.side_effect = httpx.HTTPError("Network error")

        result = update_manager.list_available_versions("owner/repo")

        assert result == []

    @patch("httpx.Client", autospec=True)
    def test_list_available_asset_versions_error(self, mock_client_class, update_manager):
        """Should handle errors gracefully and return empty list."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_client.get.side_effect = httpx.HTTPError("Network error")

        result = update_manager.list_available_asset_versions("owner/repo")

        assert result == []
