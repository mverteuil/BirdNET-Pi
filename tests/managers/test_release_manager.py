"""Tests for ReleaseManager."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from birdnetpi.managers.release_manager import ReleaseAsset, ReleaseConfig, ReleaseManager


@pytest.fixture
def mock_file_resolver(file_path_resolver, tmp_path):
    """Create a mock FilePathResolver.

    Uses the global file_path_resolver fixture as a base to prevent MagicMock file creation.
    """
    # Create test directories
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    ioc_db_path = tmp_path / "database" / "ioc_reference.db"
    ioc_db_path.parent.mkdir(parents=True, exist_ok=True)
    ioc_db_path.touch()

    # Override the methods
    file_path_resolver.get_models_dir = lambda: models_dir
    file_path_resolver.get_ioc_database_path = lambda: ioc_db_path
    return file_path_resolver


@pytest.fixture
def release_manager(mock_file_resolver, tmp_path):
    """Create a ReleaseManager instance for testing."""
    return ReleaseManager(mock_file_resolver, tmp_path)


@pytest.fixture
def sample_assets(tmp_path):
    """Create sample assets for testing."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)
    (models_dir / "model1.tflite").write_text("model1 content")
    (models_dir / "model2.tflite").write_text("model2 content")

    db_file = tmp_path / "ioc_reference.db"
    db_file.write_text("database content")

    return [
        ReleaseAsset(
            source_path=models_dir, target_name=Path("data/models"), description="BirdNET models"
        ),
        ReleaseAsset(
            source_path=db_file,
            target_name=Path("data/database/ioc_reference.db"),
            description="IOC database",
        ),
    ]


@pytest.fixture
def sample_config(sample_assets):
    """Create a sample ReleaseConfig."""
    return ReleaseConfig(
        version="1.0.0",
        asset_branch_name="assets-v1.0.0",
        commit_message="Release assets v1.0.0",
        assets=sample_assets,
        tag_name="v1.0.0",
    )


class TestReleaseAsset:
    """Test ReleaseAsset dataclass."""

    def test_release_asset_creation(self):
        """Should create ReleaseAsset with all fields."""
        asset = ReleaseAsset(
            source_path=Path("/path/to/source"),
            target_name=Path("target_name"),
            description="Asset description",
        )
        assert asset.source_path == Path("/path/to/source")
        assert asset.target_name == Path("target_name")
        assert asset.description == "Asset description"


class TestReleaseConfig:
    """Test ReleaseConfig dataclass."""

    def test_release_config_creation(self):
        """Should create ReleaseConfig with all fields."""
        assets = [ReleaseAsset(Path("/source"), Path("target"), "desc")]
        config = ReleaseConfig(
            version="1.0.0",
            asset_branch_name="assets-v1.0.0",
            commit_message="Release message",
            assets=assets,
            tag_name="v1.0.0",
        )
        assert config.version == "1.0.0"
        assert config.asset_branch_name == "assets-v1.0.0"
        assert config.commit_message == "Release message"
        assert config.assets == assets
        assert config.tag_name == "v1.0.0"

    def test_release_config_optional_tag_name(self):
        """Should create ReleaseConfig with optional tag_name."""
        assets = [ReleaseAsset(Path("/source"), Path("target"), "desc")]
        config = ReleaseConfig(
            version="1.0.0",
            asset_branch_name="assets-v1.0.0",
            commit_message="Release message",
            assets=assets,
        )
        assert config.tag_name is None


class TestReleaseManager:
    """Test ReleaseManager functionality."""

    def test_init__repo_path(self, mock_file_resolver, tmp_path):
        """Should initialize with provided repo path."""
        manager = ReleaseManager(mock_file_resolver, tmp_path)
        assert manager.file_resolver == mock_file_resolver
        assert manager.repo_path == tmp_path

    def test_init_without_repo_path(self, mock_file_resolver):
        """Should initialize with current directory as repo path."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/current/dir")
            manager = ReleaseManager(mock_file_resolver)
            assert manager.repo_path == Path("/current/dir")

    def test_validate_assets_exist(self, release_manager, sample_assets):
        """Should pass validation when all assets exist."""
        # Should not raise any exception
        release_manager._validate_assets_exist(sample_assets)

    def test_validate_assets_exist__missing_asset(self, release_manager):
        """Should raise FileNotFoundError for missing assets."""
        missing_assets = [ReleaseAsset(Path("/nonexistent/path"), Path("target"), "description")]
        with pytest.raises(FileNotFoundError, match="Missing assets"):
            release_manager._validate_assets_exist(missing_assets)

    def test_get_current_branch(self, release_manager):
        """Should return current branch name."""
        with patch.object(release_manager, "_run_git_command") as mock_git:
            mock_git.return_value = "main\n"
            branch = release_manager._get_current_branch()
            assert branch == "main"
            mock_git.assert_called_once_with(["branch", "--show-current"], capture_output=True)

    def test_get_current_branch_error(self, release_manager):
        """Should return 'main' as fallback on error."""
        with patch.object(release_manager, "_run_git_command") as mock_git:
            mock_git.side_effect = subprocess.CalledProcessError(1, "git")
            branch = release_manager._get_current_branch()
            assert branch == "main"

    def test_create_asset_gitignore(self, release_manager):
        """Should create .gitignore file with proper content."""
        release_manager._create_asset_gitignore()
        gitignore_path = release_manager.repo_path / ".gitignore"
        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert "# System files" in content
        assert "data/ directory is NOT excluded" in content

    def test_create_asset_readme(self, release_manager, sample_config):
        """Should create README file with proper content."""
        release_manager._create_asset_readme(sample_config)
        readme_path = release_manager.repo_path / "README.md"
        assert readme_path.exists()
        content = readme_path.read_text()
        assert "BirdNET-Pi Release Assets - 1.0.0" in content
        assert "data/models" in content
        assert "BirdNET models" in content

    def test_generate_release_notes(self, release_manager, sample_config):
        """Should generate proper release notes."""
        notes = release_manager._generate_release_notes(sample_config, "abc123")
        assert "BirdNET-Pi 1.0.0" in notes
        assert "data/models" in notes
        assert "BirdNET models" in notes
        assert "assets-v1.0.0" in notes
        assert "abc123" in notes

    def test_build_release_info(self, release_manager, sample_config):
        """Should build proper release info dictionary."""
        info = release_manager._build_release_info(sample_config, "abc123")
        assert info["version"] == "1.0.0"
        assert info["asset_tag"] == "assets-v1.0.0"
        assert info["commit_sha"] == "abc123"
        assert len(info["assets"]) == 2
        assert info["assets"][0]["name"] == "data/models"

    def test_get_default_assets(self, release_manager, mock_file_resolver):
        """Should return default assets with proper paths."""
        assets = release_manager.get_default_assets()
        assert len(assets) == 4

        models_asset = assets[0]
        assert models_asset.target_name == Path("data/models")
        assert "BirdNET TensorFlow Lite models" in models_asset.description

        ioc_db_asset = assets[1]
        assert ioc_db_asset.target_name == Path("data/database/ioc_reference.db")
        assert "IOC World Bird Names" in ioc_db_asset.description

        avibase_asset = assets[2]
        assert avibase_asset.target_name == Path("data/database/avibase_database.db")
        assert "Avibase multilingual" in avibase_asset.description

        patlevin_asset = assets[3]
        assert patlevin_asset.target_name == Path("data/database/patlevin_database.db")
        assert "Patrick Levin" in patlevin_asset.description

    def test_get_asset_path_dev_exists(self, release_manager, tmp_path):
        """Should prefer dev path when it exists."""
        dev_path = Path("data/models")
        dev_full_path = tmp_path / dev_path
        dev_full_path.mkdir(parents=True)

        result = release_manager._get_asset_path(dev_path, "/prod/path")
        assert result == dev_full_path

    def test_get_asset_path_dev_not_exists(self, release_manager):
        """Should use production path when dev path doesn't exist."""
        result = release_manager._get_asset_path("nonexistent/path", "/prod/path")
        assert result == Path("/prod/path")

    @patch("subprocess.run")
    def test_run_command(self, mock_run, release_manager):
        """Should run command successfully."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "output"

        result = release_manager._run_command(["echo", "test"], capture_output=True)
        assert result == "output"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run, release_manager):
        """Should handle command failure properly."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "output"
        mock_run.return_value.stderr = "error"

        with pytest.raises(subprocess.CalledProcessError):
            release_manager._run_command(["false"], check=True)

    @patch("subprocess.run")
    def test_run_git_command(self, mock_run, release_manager):
        """Should run git command with proper arguments."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "git output"

        result = release_manager._run_git_command(["status"], capture_output=True)
        assert result == "git output"

        # Check that git was called with the right arguments
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "git"
        assert "status" in call_args

    @patch("shutil.copy2")
    @patch("shutil.copytree")
    def test_copy_assets_to_branch_file(self, mock_copytree, mock_copy2, release_manager, tmp_path):
        """Should copy file assets correctly."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        assets = [ReleaseAsset(source_file, Path("target.txt"), "description")]
        release_manager._copy_assets_to_branch(assets)

        mock_copy2.assert_called_once()
        mock_copytree.assert_not_called()

    @patch("shutil.copy2")
    @patch("shutil.copytree")
    def test_copy_assets_to_branch_directory(
        self, mock_copytree, mock_copy2, release_manager, tmp_path
    ):
        """Should copy directory assets correctly."""
        source_dir = tmp_path / "source_dir"
        source_dir.mkdir()

        assets = [ReleaseAsset(source_dir, Path("target_dir"), "description")]
        release_manager._copy_assets_to_branch(assets)

        mock_copytree.assert_called_once()
        mock_copy2.assert_not_called()

    @patch.object(ReleaseManager, "_run_git_command")
    def test_commit_assets(self, mock_git, release_manager, sample_config):
        """Should commit assets with proper git commands."""
        release_manager._commit_assets(sample_config)

        # Check that git add was called for each asset
        git_calls = mock_git.call_args_list
        add_calls = [call for call in git_calls if call[0][0][0] == "add"]
        assert len(add_calls) >= 2  # At least for assets

    @patch.object(ReleaseManager, "_run_command")
    def test_create_github_release(self, mock_run, release_manager, sample_config):
        """Should create GitHub release with proper command."""
        mock_run.return_value = "https://github.com/user/repo/releases/tag/v1.0.0"

        result = release_manager.create_github_release(sample_config, "abc123")

        assert result["tag_name"] == "v1.0.0"
        assert result["asset_commit_sha"] == "abc123"
        assert "github.com" in result["release_url"]

        # Check that gh command was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gh"
        assert "release" in call_args
        assert "create" in call_args

    @patch.object(ReleaseManager, "_cleanup_and_return_to_branch")
    @patch.object(ReleaseManager, "_create_orphaned_commit")
    @patch.object(ReleaseManager, "_get_current_branch")
    @patch.object(ReleaseManager, "_validate_assets_exist")
    def test_create_asset_release(
        self,
        mock_validate,
        mock_get_branch,
        mock_create_commit,
        mock_cleanup,
        release_manager,
        sample_config,
    ):
        """Should create asset release successfully."""
        mock_get_branch.return_value = "main"
        mock_create_commit.return_value = "abc123"

        result = release_manager.create_asset_release(sample_config)

        assert result["version"] == "1.0.0"
        assert result["commit_sha"] == "abc123"
        assert result["asset_tag"] == "assets-v1.0.0"

        mock_validate.assert_called_once()
        mock_get_branch.assert_called_once()
        mock_create_commit.assert_called_once()
        mock_cleanup.assert_called_once_with("main")

    @patch.object(ReleaseManager, "_cleanup_and_return_to_branch")
    @patch.object(ReleaseManager, "_create_orphaned_commit")
    @patch.object(ReleaseManager, "_get_current_branch")
    @patch.object(ReleaseManager, "_validate_assets_exist")
    def test_create_asset_release__cleanup_on_error(
        self,
        mock_validate,
        mock_get_branch,
        mock_create_commit,
        mock_cleanup,
        release_manager,
        sample_config,
    ):
        """Should cleanup even when commit creation fails."""
        mock_get_branch.return_value = "main"
        mock_create_commit.side_effect = Exception("Commit failed")

        with pytest.raises(Exception, match="Commit failed"):
            release_manager.create_asset_release(sample_config)

        mock_cleanup.assert_called_once_with("main")

    @patch("tempfile.TemporaryDirectory")
    @patch("shutil.copy2")
    @patch("shutil.copytree")
    @patch.object(ReleaseManager, "_run_git_command")
    def test_create_orphaned_commit_integration(
        self,
        mock_git,
        mock_copytree,
        mock_copy2,
        mock_tempdir,
        release_manager,
        sample_config,
        tmp_path,
    ):
        """Should create orphaned commit with all steps."""
        # Mock temporary directory
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        mock_tempdir.return_value.__enter__.return_value = str(temp_dir)

        # Mock git commands
        mock_git.return_value = "abc123"

        # Create the assets that will be referenced
        for asset in sample_config.assets:
            source_path = Path(asset.source_path)
            if not source_path.exists():
                if asset.target_name.endswith(".db"):
                    source_path.write_text("db content")
                else:
                    source_path.mkdir(parents=True, exist_ok=True)

        result = release_manager._create_orphaned_commit(sample_config)

        assert result == "abc123"
        # Verify git commands were called in sequence
        git_calls = mock_git.call_args_list
        assert any("checkout" in str(call) and "--orphan" in str(call) for call in git_calls)
        assert any("tag" in str(call) for call in git_calls)
        assert any("push" in str(call) for call in git_calls)

    @patch.object(ReleaseManager, "_run_git_command")
    def test_cleanup__return_to_branch(self, mock_git, release_manager):
        """Should cleanup and return to original branch successfully."""
        mock_git.side_effect = [
            None,  # checkout original branch
            "  temp-assets-v1.0.0\n* main\n",  # branch list
            None,  # delete temp branch
        ]

        release_manager._cleanup_and_return_to_branch("main")

        # Should attempt checkout, list branches, and delete temp branch
        assert mock_git.call_count >= 2

    @patch.object(ReleaseManager, "_run_git_command")
    def test_cleanup__return_to_branch_checkout_failure(self, mock_git, release_manager):
        """Should handle checkout failure with reset and retry."""
        mock_git.side_effect = [
            subprocess.CalledProcessError(1, "git checkout"),  # checkout fails
            None,  # reset --hard
            None,  # clean -fxd
            None,  # retry checkout
        ]

        release_manager._cleanup_and_return_to_branch("main")

        # Should attempt reset and clean after checkout failure
        git_calls = mock_git.call_args_list
        assert any("reset" in str(call) and "--hard" in str(call) for call in git_calls)
        assert any("clean" in str(call) for call in git_calls)
