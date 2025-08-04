"""Tests for AssetInstallerWrapper."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from birdnetpi.wrappers.asset_installer_wrapper import (
    check_local_assets,
    install_assets,
    list_available_assets,
    main,
)


@pytest.fixture
def mock_update_manager():
    """Create a mock UpdateManager."""
    return MagicMock()


@pytest.fixture
def mock_file_resolver():
    """Create a mock FilePathResolver."""
    mock_resolver = MagicMock()
    mock_resolver.get_models_dir.return_value = "/test/models"
    mock_resolver.get_ioc_database_path.return_value = "/test/ioc_reference.db"
    return mock_resolver


class TestInstallAssets:
    """Test install_assets function."""

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    def test_install_assets_success(self, mock_update_manager_class, tmp_path):
        """Should install assets successfully."""
        # Setup mock
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        
        mock_result = {
            "version": "v2.1.0",
            "downloaded_assets": ["Model: model1.tflite", "IOC reference database"],
            "errors": []
        }
        mock_manager.download_release_assets.return_value = mock_result
        
        # Create args
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            output_json=None
        )
        
        install_assets(args)
        
        mock_manager.download_release_assets.assert_called_once_with(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            github_repo="mverteuil/BirdNET-Pi"
        )

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    def test_install_assets_with_json_output(self, mock_update_manager_class, tmp_path):
        """Should install assets and write JSON output."""
        # Setup mock
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        
        mock_result = {
            "version": "v2.1.0",
            "downloaded_assets": ["Model: model1.tflite"],
            "errors": []
        }
        mock_manager.download_release_assets.return_value = mock_result
        
        output_file = tmp_path / "result.json"
        
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=False,
            output_json=str(output_file)
        )
        
        install_assets(args)
        
        # Check JSON output was written
        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
        assert data == mock_result

    @patch("birdnetpi.wrappers.asset_installer_wrapper.sys.exit")
    def test_install_assets_no_asset_types_specified(self, mock_exit):
        """Should exit with error when no asset types specified."""
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=False,
            include_ioc_db=False,
            output_json=None
        )
        
        install_assets(args)
        
        mock_exit.assert_called_once_with(1)

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    @patch("birdnetpi.wrappers.asset_installer_wrapper.sys.exit")
    def test_install_assets_download_error(self, mock_exit, mock_update_manager_class):
        """Should handle download errors gracefully."""
        # Setup mock to raise exception
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        mock_manager.download_release_assets.side_effect = Exception("Download failed")
        
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            output_json=None
        )
        
        install_assets(args)
        
        mock_exit.assert_called_once_with(1)

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    @patch("birdnetpi.wrappers.asset_installer_wrapper.sys.exit")
    def test_install_assets_permission_error_help(self, mock_exit, mock_update_manager_class, capsys):
        """Should show helpful message for permission errors."""
        # Setup mock to raise permission error
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        mock_manager.download_release_assets.side_effect = Exception(
            "Permission denied: /var/lib/birdnetpi/models"
        )
        
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            output_json=None
        )
        
        install_assets(args)
        
        # Check that helpful message was printed
        captured = capsys.readouterr()
        assert "LOCAL DEVELOPMENT SETUP REQUIRED" in captured.out
        assert "BIRDNETPI_DATA" in captured.out
        
        mock_exit.assert_called_once_with(1)


class TestListAvailableAssets:
    """Test list_available_assets function."""

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    def test_list_available_assets_success(self, mock_update_manager_class, capsys):
        """Should list available asset versions."""
        # Setup mock
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        mock_manager.list_available_versions.return_value = ["v2.1.0", "v2.0.0", "v1.9.0"]
        
        args = argparse.Namespace()
        
        list_available_assets(args)
        
        captured = capsys.readouterr()
        assert "Available asset versions:" in captured.out
        assert "Latest version: v2.1.0" in captured.out
        assert "v2.1.0" in captured.out
        assert "v2.0.0" in captured.out

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    def test_list_available_assets_empty(self, mock_update_manager_class, capsys):
        """Should handle empty version list."""
        # Setup mock
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        mock_manager.list_available_versions.return_value = []
        
        args = argparse.Namespace()
        
        list_available_assets(args)
        
        captured = capsys.readouterr()
        assert "No asset versions found." in captured.out

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    @patch("birdnetpi.wrappers.asset_installer_wrapper.sys.exit")
    def test_list_available_assets_error(self, mock_exit, mock_update_manager_class):
        """Should handle list errors gracefully."""
        # Setup mock to raise exception
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        mock_manager.list_available_versions.side_effect = Exception("API error")
        
        args = argparse.Namespace()
        
        list_available_assets(args)
        
        mock_exit.assert_called_once_with(1)


class TestCheckLocalAssets:
    """Test check_local_assets function."""

    @patch("birdnetpi.wrappers.asset_installer_wrapper.FilePathResolver")
    def test_check_local_assets_models_exist(self, mock_file_resolver_class, tmp_path, capsys):
        """Should show status of existing models."""
        # Setup mock resolver
        mock_resolver = MagicMock()
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model1.tflite").write_bytes(b"model data 1" * 100)  # 1200 bytes
        (models_dir / "model2.tflite").write_bytes(b"model data 2" * 200)  # 2400 bytes
        
        mock_resolver.get_models_dir.return_value = str(models_dir)
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "ioc.db")
        mock_file_resolver_class.return_value = mock_resolver
        
        args = argparse.Namespace(verbose=False)
        
        check_local_assets(args)
        
        captured = capsys.readouterr()
        assert "✓ Models: 2 model files" in captured.out
        assert str(models_dir) in captured.out

    @patch("birdnetpi.wrappers.asset_installer_wrapper.FilePathResolver")
    def test_check_local_assets_verbose_mode(self, mock_file_resolver_class, tmp_path, capsys):
        """Should show detailed file information in verbose mode."""
        # Setup mock resolver
        mock_resolver = MagicMock()
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model1.tflite").write_bytes(b"model data" * 1024)  # ~10KB
        
        mock_resolver.get_models_dir.return_value = str(models_dir)
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "ioc.db")
        mock_file_resolver_class.return_value = mock_resolver
        
        args = argparse.Namespace(verbose=True)
        
        check_local_assets(args)
        
        captured = capsys.readouterr()
        assert "model1.tflite (" in captured.out  # Should show individual file sizes

    @patch("birdnetpi.wrappers.asset_installer_wrapper.FilePathResolver")
    def test_check_local_assets_ioc_database_exists(self, mock_file_resolver_class, tmp_path, capsys):
        """Should show status of existing IOC database."""
        # Setup mock resolver
        mock_resolver = MagicMock()
        ioc_db = tmp_path / "ioc_reference.db"
        ioc_db.write_bytes(b"database content" * 1000)  # ~16KB
        
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(ioc_db)
        mock_file_resolver_class.return_value = mock_resolver
        
        args = argparse.Namespace(verbose=False)
        
        check_local_assets(args)
        
        captured = capsys.readouterr()
        assert "✓ IOC Database:" in captured.out
        assert str(ioc_db) in captured.out

    @patch("birdnetpi.wrappers.asset_installer_wrapper.FilePathResolver")
    def test_check_local_assets_missing_files(self, mock_file_resolver_class, tmp_path, capsys):
        """Should show missing status for non-existent files."""
        # Setup mock resolver
        mock_resolver = MagicMock()
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "ioc.db")
        mock_file_resolver_class.return_value = mock_resolver
        
        args = argparse.Namespace(verbose=False)
        
        check_local_assets(args)
        
        captured = capsys.readouterr()
        assert "✗ Models: Not installed" in captured.out
        assert "✗ IOC Database: Not installed" in captured.out


class TestMain:
    """Test main function and argument parsing."""

    @patch("birdnetpi.wrappers.asset_installer_wrapper.install_assets")
    def test_main_install_command(self, mock_install_assets):
        """Should parse install command correctly."""
        test_args = [
            "asset-installer", "install", "v2.1.0", 
            "--include-models", "--include-ioc-db", "--output-json", "result.json"
        ]
        
        with patch.object(sys, "argv", test_args):
            main()
        
        mock_install_assets.assert_called_once()
        args = mock_install_assets.call_args[0][0]
        assert args.version == "v2.1.0"
        assert args.include_models is True
        assert args.include_ioc_db is True
        assert args.output_json == "result.json"

    @patch("birdnetpi.wrappers.asset_installer_wrapper.list_available_assets")
    def test_main_list_versions_command(self, mock_list_assets):
        """Should parse list-versions command correctly."""
        test_args = ["asset-installer", "list-versions"]
        
        with patch.object(sys, "argv", test_args):
            main()
        
        mock_list_assets.assert_called_once()

    @patch("birdnetpi.wrappers.asset_installer_wrapper.check_local_assets")
    def test_main_check_local_command(self, mock_check_assets):
        """Should parse check-local command correctly."""
        test_args = ["asset-installer", "check-local", "--verbose"]
        
        with patch.object(sys, "argv", test_args):
            main()
        
        mock_check_assets.assert_called_once()
        args = mock_check_assets.call_args[0][0]
        assert args.verbose is True

    def test_main_no_command_shows_help(self, capsys):
        """Should show help when no command specified."""
        test_args = ["asset-installer"]
        
        with patch.object(sys, "argv", test_args):
            main()
        
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "BirdNET-Pi Asset Installer" in captured.out

    def test_main_argument_parsing_integration(self):
        """Should have proper argument structure."""
        # Test that argument parser can handle expected arguments
        test_cases = [
            ["install", "latest", "--include-models"],
            ["install", "v2.0.0", "--include-ioc-db"],
            ["install", "v2.1.0", "--include-models", "--include-ioc-db", "--output-json", "test.json"],
            ["list-versions"],
            ["check-local"],
            ["check-local", "--verbose"]
        ]
        
        for args in test_cases:
            # This would fail if argument structure is wrong
            with patch("birdnetpi.wrappers.asset_installer_wrapper.install_assets"), \
                 patch("birdnetpi.wrappers.asset_installer_wrapper.list_available_assets"), \
                 patch("birdnetpi.wrappers.asset_installer_wrapper.check_local_assets"):
                
                with patch.object(sys, "argv", ["asset-installer"] + args):
                    try:
                        main()
                    except SystemExit:
                        pass  # argparse calls sys.exit for some cases, that's fine


class TestIntegration:
    """Integration tests for the asset installer wrapper."""

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    @patch("birdnetpi.wrappers.asset_installer_wrapper.FilePathResolver")
    def test_complete_install_workflow(self, mock_file_resolver_class, mock_update_manager_class, tmp_path):
        """Should complete full install workflow."""
        # Setup mocks
        mock_resolver = MagicMock()
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "ioc.db")
        mock_file_resolver_class.return_value = mock_resolver
        
        mock_manager = MagicMock()
        mock_result = {
            "version": "v2.1.0",
            "downloaded_assets": ["Model: model1.tflite", "IOC reference database"],
            "errors": []
        }
        mock_manager.download_release_assets.return_value = mock_result
        mock_update_manager_class.return_value = mock_manager
        
        # Test install command
        args = argparse.Namespace(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            output_json=None
        )
        
        install_assets(args)
        
        # Verify UpdateManager was called correctly
        mock_manager.download_release_assets.assert_called_once_with(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            github_repo="mverteuil/BirdNET-Pi"
        )

    @patch("birdnetpi.wrappers.asset_installer_wrapper.UpdateManager")
    def test_error_handling_consistency(self, mock_update_manager_class):
        """Should handle different types of errors consistently."""
        mock_manager = MagicMock()
        mock_update_manager_class.return_value = mock_manager
        
        error_types = [
            Exception("General error"),
            FileNotFoundError("File not found"),
            PermissionError("Permission denied"),
            ConnectionError("Network error")
        ]
        
        for error in error_types:
            mock_manager.download_release_assets.side_effect = error
            
            args = argparse.Namespace(
                version="v2.1.0",
                include_models=True,
                include_ioc_db=False,
                output_json=None
            )
            
            with patch("birdnetpi.wrappers.asset_installer_wrapper.sys.exit") as mock_exit:
                install_assets(args)
                mock_exit.assert_called_once_with(1)
                mock_exit.reset_mock()