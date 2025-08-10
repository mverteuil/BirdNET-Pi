"""Tests for release wrapper."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.managers.release_manager import ReleaseAsset
from birdnetpi.wrappers.release_wrapper import (
    _add_custom_assets,
    _build_asset_list,
    _handle_github_release,
    create_release,
    list_assets,
    main,
)


@pytest.fixture
def mock_release_manager():
    """Create a mock ReleaseManager."""
    mock_manager = MagicMock()
    mock_manager.get_default_assets.return_value = [
        ReleaseAsset(Path("/test/models"), Path("data/models"), "BirdNET models"),
        ReleaseAsset(Path("/test/ioc.db"), Path("data/database/ioc_reference.db"), "IOC database"),
    ]
    return mock_manager


@pytest.fixture
def mock_file_resolver():
    """Create a mock FilePathResolver."""
    return MagicMock()


class TestBuildAssetList:
    """Test _build_asset_list function."""

    def test_build_asset_list__models(self, mock_release_manager, tmp_path):
        """Should build asset list with models when they exist."""
        # Create test models directory
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model1.tflite").touch()

        # Update mock to use real path
        mock_release_manager.get_default_assets.return_value = [
            ReleaseAsset(models_dir, Path("data/models"), "BirdNET models"),
            ReleaseAsset(
                Path("/nonexistent/ioc.db"), Path("data/database/ioc_reference.db"), "IOC database"
            ),
        ]

        args = argparse.Namespace(
            include_models=True,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=None,
        )

        assets = _build_asset_list(args, mock_release_manager)

        assert len(assets) == 1
        assert assets[0].target_name == Path("data/models")
        assert assets[0].description == "BirdNET models"

    def test_build_asset_list__ioc_db(self, mock_release_manager, tmp_path):
        """Should build asset list with IOC database when it exists."""
        # Create test IOC database
        ioc_db = tmp_path / "ioc.db"
        ioc_db.touch()

        # Update mock to use real path
        mock_release_manager.get_default_assets.return_value = [
            ReleaseAsset(Path("/nonexistent/models"), Path("data/models"), "BirdNET models"),
            ReleaseAsset(ioc_db, Path("data/database/ioc_reference.db"), "IOC database"),
        ]

        args = argparse.Namespace(
            include_models=False,
            include_ioc_db=True,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=None,
        )

        assets = _build_asset_list(args, mock_release_manager)

        assert len(assets) == 1
        assert assets[0].target_name == Path("data/database/ioc_reference.db")
        assert assets[0].description == "IOC database"

    def test_build_asset_list__custom_assets(self, mock_release_manager, tmp_path):
        """Should build asset list with custom assets."""
        # Create test custom asset
        custom_file = tmp_path / "custom.txt"
        custom_file.write_text("custom content")

        args = argparse.Namespace(
            include_models=False,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=[f"{custom_file}:custom/path:Custom asset description"],
        )

        assets = _build_asset_list(args, mock_release_manager)

        assert len(assets) == 1
        assert assets[0].source_path == custom_file
        assert assets[0].target_name == Path("custom/path")
        assert assets[0].description == "Custom asset description"

    @patch("birdnetpi.wrappers.release_wrapper.sys.exit")
    def test_build_asset_list__missing_models_warning(
        self, mock_exit, mock_release_manager, capsys
    ):
        """Should warn when models are requested but missing."""
        mock_exit.side_effect = SystemExit(1)
        args = argparse.Namespace(
            include_models=True,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=None,
        )

        with pytest.raises(SystemExit):
            _build_asset_list(args, mock_release_manager)

        captured = capsys.readouterr()
        assert "Warning: Models not found at expected locations" in captured.out
        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.release_wrapper.sys.exit")
    def test_build_asset_list__no_assets(self, mock_exit, mock_release_manager):
        """Should exit when no assets are specified."""
        mock_exit.side_effect = SystemExit(1)
        args = argparse.Namespace(
            include_models=False,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=None,
        )

        with pytest.raises(SystemExit):
            _build_asset_list(args, mock_release_manager)

        mock_exit.assert_called_once_with(1)


class TestAddCustomAssets:
    """Test _add_custom_assets function."""

    def test_add_custom_assets_valid_format(self, tmp_path):
        """Should add custom assets with valid format."""
        # Create test files
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1")
        file2 = tmp_path / "file2.txt"
        file2.write_text("content2")

        custom_assets = [f"{file1}:target1:Description 1", f"{file2}:target2:Description 2"]
        assets = []

        _add_custom_assets(custom_assets, assets)

        assert len(assets) == 2
        assert assets[0].source_path == file1
        assert assets[0].target_name == Path("target1")
        assert assets[0].description == "Description 1"
        assert assets[1].source_path == file2
        assert assets[1].target_name == Path("target2")
        assert assets[1].description == "Description 2"

    @patch("birdnetpi.wrappers.release_wrapper.sys.exit")
    def test_add_custom_assets__invalid_format(self, mock_exit):
        """Should exit when custom asset format is invalid."""
        mock_exit.side_effect = SystemExit(1)
        custom_assets = ["invalid:format"]  # Missing description
        assets = []

        with pytest.raises(SystemExit):
            _add_custom_assets(custom_assets, assets)

        mock_exit.assert_called_once_with(1)

    @patch("birdnetpi.wrappers.release_wrapper.sys.exit")
    def test_add_custom_assets__missing_file(self, mock_exit):
        """Should exit when custom asset file doesn't exist."""
        mock_exit.side_effect = SystemExit(1)
        custom_assets = ["/nonexistent/file:target:Description"]
        assets = []

        with pytest.raises(SystemExit):
            _add_custom_assets(custom_assets, assets)

        mock_exit.assert_called_once_with(1)


class TestHandleGithubRelease:
    """Test _handle_github_release function."""

    def test_handle_github_release_disabled(self, mock_release_manager):
        """Should return None when GitHub release is disabled."""
        args = argparse.Namespace(create_github_release=False)
        config = MagicMock()
        asset_result = {"commit_sha": "abc123"}

        result = _handle_github_release(args, config, mock_release_manager, asset_result)

        assert result is None
        mock_release_manager.create_github_release.assert_not_called()

    def test_handle_github_release_enabled(self, mock_release_manager, capsys):
        """Should create GitHub release when enabled."""
        mock_github_result = {
            "tag_name": "v2.1.0",
            "release_url": "https://github.com/user/repo/releases/tag/v2.1.0",
            "asset_commit_sha": "abc123",
        }
        mock_release_manager.create_github_release.return_value = mock_github_result

        args = argparse.Namespace(create_github_release=True)
        config = MagicMock()
        asset_result = {"commit_sha": "abc123"}

        result = _handle_github_release(args, config, mock_release_manager, asset_result)

        assert result == mock_github_result
        mock_release_manager.create_github_release.assert_called_once_with(config, "abc123")

        captured = capsys.readouterr()
        assert "Creating GitHub release..." in captured.out
        assert "GitHub release created: v2.1.0" in captured.out
        assert "Release URL: https://github.com/user/repo/releases/tag/v2.1.0" in captured.out

    def test_handle_github_release__no_url(self, mock_release_manager, capsys):
        """Should handle GitHub release without URL."""
        mock_github_result = {
            "tag_name": "v2.1.0",
            "release_url": None,
            "asset_commit_sha": "abc123",
        }
        mock_release_manager.create_github_release.return_value = mock_github_result

        args = argparse.Namespace(create_github_release=True)
        config = MagicMock()
        asset_result = {"commit_sha": "abc123"}

        result = _handle_github_release(args, config, mock_release_manager, asset_result)

        assert result == mock_github_result

        captured = capsys.readouterr()
        assert "GitHub release created: v2.1.0" in captured.out
        assert "Release URL:" not in captured.out  # Should not show URL line


class TestCreateRelease:
    """Test create_release function."""

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    @patch("birdnetpi.wrappers.release_wrapper._build_asset_list")
    @patch("birdnetpi.wrappers.release_wrapper._handle_github_release")
    def test_create_release(
        self,
        mock_handle_github,
        mock_build_assets,
        mock_manager_class,
        mock_resolver_class,
        tmp_path,
        capsys,
    ):
        """Should create release successfully."""
        # Setup mocks with proper paths to prevent MagicMock folder creation
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        mock_assets = [ReleaseAsset(Path("/test/models"), Path("data/models"), "Models")]
        mock_build_assets.return_value = mock_assets

        mock_asset_result = {
            "version": "v2.1.0",
            "asset_branch": "assets-v2.1.0",
            "commit_sha": "abc123",
            "assets": ["data/models"],
        }
        mock_manager.create_asset_release.return_value = mock_asset_result

        mock_handle_github.return_value = None

        # Create args
        args = argparse.Namespace(
            version="v2.1.0",
            asset_branch=None,
            commit_message=None,
            tag_name=None,
            create_github_release=False,
            output_json=None,
        )

        create_release(args)

        # Verify calls
        mock_manager_class.assert_called_once_with(mock_resolver)
        mock_build_assets.assert_called_once_with(args, mock_manager)
        mock_manager.create_asset_release.assert_called_once()

        # Check output
        captured = capsys.readouterr()
        assert "Creating orphaned commit with release assets..." in captured.out
        assert "Asset release created successfully!" in captured.out
        assert "Version: v2.1.0" in captured.out

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    @patch("birdnetpi.wrappers.release_wrapper._build_asset_list")
    def test_create_release__custom_options(
        self, mock_build_assets, mock_manager_class, mock_resolver_class
    ):
        """Should create release with custom branch and commit message."""
        # Setup mocks with proper paths to prevent MagicMock folder creation
        from pathlib import Path

        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = Path("/tmp/test/ioc_reference.db")
        mock_resolver.get_models_dir.return_value = Path("/tmp/test/models")
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        mock_assets = [ReleaseAsset(Path("/test/models"), Path("data/models"), "Models")]
        mock_build_assets.return_value = mock_assets

        mock_asset_result = {
            "version": "v2.1.0",
            "asset_branch": "custom-branch",
            "commit_sha": "abc123",
            "assets": ["data/models"],
        }
        mock_manager.create_asset_release.return_value = mock_asset_result

        # Create args with custom options
        args = argparse.Namespace(
            version="v2.1.0",
            asset_branch="custom-branch",
            commit_message="Custom commit message",
            tag_name="custom-tag",
            create_github_release=False,
            output_json=None,
        )

        create_release(args)

        # Verify config was created with custom options
        config_call = mock_manager.create_asset_release.call_args[0][0]
        assert config_call.version == "v2.1.0"
        assert config_call.asset_branch_name == "custom-branch"
        assert config_call.commit_message == "Custom commit message"
        assert config_call.tag_name == "custom-tag"

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    @patch("birdnetpi.wrappers.release_wrapper._build_asset_list")
    @patch("birdnetpi.wrappers.release_wrapper._handle_github_release")
    def test_create_release__json_output(
        self,
        mock_handle_github,
        mock_build_assets,
        mock_manager_class,
        mock_resolver_class,
        tmp_path,
    ):
        """Should create release and write JSON output."""
        # Setup mocks with proper paths to prevent MagicMock folder creation
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        mock_assets = [ReleaseAsset(Path("/test/models"), Path("data/models"), "Models")]
        mock_build_assets.return_value = mock_assets

        mock_asset_result = {
            "version": "v2.1.0",
            "asset_branch": "assets-v2.1.0",
            "commit_sha": "abc123",
            "assets": ["data/models"],
        }
        mock_manager.create_asset_release.return_value = mock_asset_result

        mock_github_result = {"tag_name": "v2.1.0"}
        mock_handle_github.return_value = mock_github_result

        output_file = tmp_path / "release.json"

        args = argparse.Namespace(
            version="v2.1.0",
            asset_branch=None,
            commit_message=None,
            tag_name=None,
            create_github_release=True,
            output_json=str(output_file),
        )

        create_release(args)

        # Check JSON output
        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)

        assert data["asset_release"] == mock_asset_result
        assert data["github_release"] == mock_github_result

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    @patch("birdnetpi.wrappers.release_wrapper._build_asset_list")
    @patch("birdnetpi.wrappers.release_wrapper.sys.exit")
    def test_create_release__error_handling(
        self, mock_exit, mock_build_assets, mock_manager_class, mock_resolver_class
    ):
        """Should handle release creation errors."""
        # Setup mocks with proper paths to prevent MagicMock folder creation
        from pathlib import Path

        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = Path("/tmp/test/ioc_reference.db")
        mock_resolver.get_models_dir.return_value = Path("/tmp/test/models")
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.create_asset_release.side_effect = Exception("Release failed")

        mock_assets = [ReleaseAsset(Path("/test/models"), Path("data/models"), "Models")]
        mock_build_assets.return_value = mock_assets

        args = argparse.Namespace(
            version="v2.1.0",
            asset_branch=None,
            commit_message=None,
            tag_name=None,
            create_github_release=False,
            output_json=None,
        )

        create_release(args)

        mock_exit.assert_called_once_with(1)


class TestListAssets:
    """Test list_assets function."""

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    def test_list_assets(self, mock_manager_class, mock_resolver_class, tmp_path, capsys):
        """Should list available assets."""
        # Create test assets
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model1.tflite").write_bytes(b"model data" * 1024)  # 10KB

        ioc_db = tmp_path / "ioc.db"
        ioc_db.write_bytes(b"db data" * 2048)  # 16KB

        # Setup mocks with proper paths to prevent MagicMock folder creation
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.get_default_assets.return_value = [
            ReleaseAsset(models_dir, Path("data/models"), "BirdNET models"),
            ReleaseAsset(ioc_db, Path("data/database/ioc_reference.db"), "IOC database"),
            ReleaseAsset(Path("/nonexistent/file"), Path("missing/asset"), "Missing asset"),
        ]

        args = argparse.Namespace()

        list_assets(args)

        captured = capsys.readouterr()
        assert "Available assets for release:" in captured.out
        assert "✓ data/models" in captured.out
        assert "✓ data/database/ioc_reference.db" in captured.out
        assert "✗ missing/asset" in captured.out
        assert "BirdNET models" in captured.out
        assert "IOC database" in captured.out

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    def test_list_assets__file_sizes(
        self, mock_manager_class, mock_resolver_class, tmp_path, capsys
    ):
        """Should show file sizes for existing assets."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"x" * (5 * 1024 * 1024))  # 5MB

        # Setup mocks with proper paths to prevent MagicMock folder creation
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.get_default_assets.return_value = [
            ReleaseAsset(test_file, Path("test/file"), "Test file")
        ]

        args = argparse.Namespace()

        list_assets(args)

        captured = capsys.readouterr()
        assert "✓ test/file (5.0 MB)" in captured.out


class TestMain:
    """Test main function and argument parsing."""

    @patch("birdnetpi.wrappers.release_wrapper.create_release")
    def test_main_create_command(self, mock_create):
        """Should parse create command correctly."""
        test_args = [
            "release-manager",
            "create",
            "v2.1.0",
            "--include-models",
            "--include-ioc-db",
            "--custom-assets",
            "file1:target1:desc1",
            "file2:target2:desc2",
            "--asset-branch",
            "custom-branch",
            "--commit-message",
            "Custom message",
            "--tag-name",
            "custom-tag",
            "--create-github-release",
            "--output-json",
            "release.json",
        ]

        with patch.object(sys, "argv", test_args):
            main()

        mock_create.assert_called_once()
        args = mock_create.call_args[0][0]
        assert args.version == "v2.1.0"
        assert args.include_models is True
        assert args.include_ioc_db is True
        assert len(args.custom_assets) == 2
        assert args.asset_branch == "custom-branch"
        assert args.commit_message == "Custom message"
        assert args.tag_name == "custom-tag"
        assert args.create_github_release is True
        assert args.output_json == "release.json"

    @patch("birdnetpi.wrappers.release_wrapper.list_assets")
    def test_main_list_assets_command(self, mock_list):
        """Should parse list-assets command correctly."""
        test_args = ["release-manager", "list-assets"]

        with patch.object(sys, "argv", test_args):
            main()

        mock_list.assert_called_once()

    def test_main__no_command_shows_help(self, capsys):
        """Should show help when no command specified."""
        test_args = ["release-manager"]

        with patch.object(sys, "argv", test_args):
            main()

        captured = capsys.readouterr()
        assert "usage:" in captured.out or "BirdNET-Pi Release Management" in captured.out

    def test_main_argument_parsing_structure(self):
        """Should have proper argument structure."""
        test_cases = [
            ["create", "v2.0.0", "--include-models"],
            ["create", "v2.1.0", "--include-ioc-db"],
            ["create", "v2.0.0", "--include-models", "--include-ioc-db", "--create-github-release"],
            ["list-assets"],
        ]

        for args in test_cases:
            with (
                patch("birdnetpi.wrappers.release_wrapper.create_release"),
                patch("birdnetpi.wrappers.release_wrapper.list_assets"),
            ):
                with patch.object(sys, "argv", ["release-manager", *args]):
                    try:
                        main()
                    except SystemExit:
                        pass  # argparse calls sys.exit for some cases, that's fine


class TestIntegration:
    """Integration tests for release wrapper."""

    @patch("birdnetpi.wrappers.release_wrapper.FilePathResolver")
    @patch("birdnetpi.wrappers.release_wrapper.ReleaseManager")
    def test_complete_create_workflow(self, mock_manager_class, mock_resolver_class, tmp_path):
        """Should complete full create workflow."""
        # Create test assets
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model1.tflite").touch()

        # Setup mocks with proper paths to prevent MagicMock folder creation
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
        mock_resolver.get_models_dir.return_value = tmp_path / "models"
        mock_resolver_class.return_value = mock_resolver

        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.get_default_assets.return_value = [
            ReleaseAsset(models_dir, Path("data/models"), "BirdNET models")
        ]

        mock_asset_result = {
            "version": "v2.1.0",
            "asset_branch": "assets-v2.1.0",
            "commit_sha": "abc123",
            "assets": ["data/models"],
        }
        mock_manager.create_asset_release.return_value = mock_asset_result

        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=None,
            asset_branch=None,
            commit_message=None,
            tag_name=None,
            create_github_release=False,
            output_json=None,
        )

        create_release(args)

        # Verify complete workflow
        mock_manager_class.assert_called_once_with(mock_resolver)
        mock_manager.create_asset_release.assert_called_once()

        # Verify config
        config = mock_manager.create_asset_release.call_args[0][0]
        assert config.version == "v2.1.0"
        assert config.asset_branch_name == "assets-v2.1.0"
        assert len(config.assets) == 1
        assert config.assets[0].target_name == Path("data/models")

    def test_edge_case_handling(self, tmp_path):
        """Should handle various edge cases properly."""
        # Test with empty custom assets list
        args = argparse.Namespace(
            include_models=False,
            include_ioc_db=False,
            include_avibase_db=False,
            include_patlevin_db=False,
            custom_assets=[],
        )

        mock_manager = MagicMock()
        mock_manager.get_default_assets.return_value = []

        with patch("birdnetpi.wrappers.release_wrapper.sys.exit") as mock_exit:
            _build_asset_list(args, mock_manager)
            mock_exit.assert_called_once_with(1)
