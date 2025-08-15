"""Test the asset_installer CLI module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.asset_installer import cli


@pytest.fixture
def test_version_data():
    """Test version data."""
    return ["v2.1.0", "v2.0.0", "v1.9.0"]


@pytest.fixture
def test_download_result():
    """Test download result data."""
    return {
        "version": "v2.1.0",
        "downloaded_assets": [
            "models/BirdNET_GLOBAL_3K_V2.4_Model_FP32.tflite",
            "data/ioc_db.sqlite",
            "data/avibase.db",
            "data/patlevin.db",
        ],
    }


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


class TestInstallAssets:
    """Test the install command."""

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_install_assets(self, mock_update_manager_class, test_download_result, runner):
        """Should install complete asset release."""
        mock_manager = MagicMock()
        mock_manager.download_release_assets.return_value = test_download_result
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["install", "v2.1.0"])

        assert result.exit_code == 0
        assert "Installing complete asset release: v2.1.0" in result.output
        assert "✓ Asset installation completed successfully!" in result.output
        assert "Version: v2.1.0" in result.output
        assert "Downloaded assets: 4" in result.output

        # Verify all assets are always downloaded
        mock_manager.download_release_assets.assert_called_once_with(
            version="v2.1.0",
            include_models=True,
            include_ioc_db=True,
            include_avibase_db=True,
            include_patlevin_db=True,
            github_repo="mverteuil/BirdNET-Pi",
        )

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_install_assets_json_output(
        self, mock_update_manager_class, test_download_result, tmp_path, runner
    ):
        """Should save installation data to JSON when requested."""
        mock_manager = MagicMock()
        mock_manager.download_release_assets.return_value = test_download_result
        mock_update_manager_class.return_value = mock_manager

        output_file = tmp_path / "install.json"

        result = runner.invoke(cli, ["install", "v2.1.0", "--output-json", str(output_file)])

        assert result.exit_code == 0
        assert f"Installation data written to: {output_file}" in result.output

        # Check JSON file contents
        assert output_file.exists()
        json_data = json.loads(output_file.read_text())
        assert json_data == test_download_result

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_install_assets_download_error(self, mock_update_manager_class, runner):
        """Should handle download errors gracefully."""
        mock_manager = MagicMock()
        mock_manager.download_release_assets.side_effect = Exception("Download failed")
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["install", "v2.1.0"])

        assert result.exit_code == 1
        assert "✗ Error installing assets: Download failed" in result.output

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_install_assets_permission_error_help(self, mock_update_manager_class, runner):
        """Should show helpful message for permission errors."""
        mock_manager = MagicMock()
        mock_manager.download_release_assets.side_effect = PermissionError(
            "Permission denied: /var/lib/birdnetpi/models"
        )
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["install", "v2.1.0"])

        assert result.exit_code == 1
        assert "✗ Error installing assets:" in result.output
        assert "LOCAL DEVELOPMENT SETUP REQUIRED" in result.output
        assert "export BIRDNETPI_DATA=./data" in result.output
        assert "uv run asset-installer install v2.1.0" in result.output


class TestListVersions:
    """Test the list-versions command."""

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_list_versions(self, mock_update_manager_class, test_version_data, runner):
        """Should list available asset versions."""
        mock_manager = MagicMock()
        mock_manager.list_available_versions.return_value = test_version_data
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["list-versions"])

        assert result.exit_code == 0
        assert "Available asset versions:" in result.output
        assert "Latest version: v2.1.0" in result.output
        assert "• v2.1.0" in result.output
        assert "• v2.0.0" in result.output
        assert "• v1.9.0" in result.output

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_list_versions_empty(self, mock_update_manager_class, runner):
        """Should handle empty version list."""
        mock_manager = MagicMock()
        mock_manager.list_available_versions.return_value = []
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["list-versions"])

        assert result.exit_code == 0
        assert "No asset versions found." in result.output

    @patch("birdnetpi.cli.asset_installer.UpdateManager")
    def test_list_versions_error(self, mock_update_manager_class, runner):
        """Should handle listing errors gracefully."""
        mock_manager = MagicMock()
        mock_manager.list_available_versions.side_effect = Exception("API error")
        mock_update_manager_class.return_value = mock_manager

        result = runner.invoke(cli, ["list-versions"])

        assert result.exit_code == 1
        assert "✗ Error listing available assets: API error" in result.output


class TestCheckLocal:
    """Test the check-local command."""

    @patch("birdnetpi.cli.asset_installer.FilePathResolver")
    def test_check_local_assets_exist(self, mock_file_resolver_class, tmp_path, runner):
        """Should report existing assets."""
        mock_resolver = MagicMock()
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "data" / "ioc_db.sqlite")
        mock_resolver.get_data_dir.return_value = str(tmp_path / "data")
        mock_file_resolver_class.return_value = mock_resolver

        # Create test files
        models_dir = tmp_path / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "model1.tflite").write_bytes(b"model" * 1000)
        (models_dir / "model2.tflite").write_bytes(b"model" * 2000)

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "ioc_db.sqlite").write_bytes(b"database" * 1000)
        (data_dir / "avibase.db").write_bytes(b"avibase" * 500)
        (data_dir / "patlevin.db").write_bytes(b"patlevin" * 750)

        result = runner.invoke(cli, ["check-local"])

        assert result.exit_code == 0
        assert "✓ Models: 2 model files" in result.output
        assert "✓ IOC Database:" in result.output
        assert "✓ Avibase Database:" in result.output
        assert "✓ PatLevin Database:" in result.output

    @patch("birdnetpi.cli.asset_installer.FilePathResolver")
    def test_check_local_verbose_mode(self, mock_file_resolver_class, tmp_path, runner):
        """Should show detailed info in verbose mode."""
        mock_resolver = MagicMock()
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "data" / "ioc_db.sqlite")
        mock_resolver.get_data_dir.return_value = str(tmp_path / "data")
        mock_file_resolver_class.return_value = mock_resolver

        # Create test files
        models_dir = tmp_path / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "model1.tflite").write_bytes(b"model" * 1000)

        result = runner.invoke(cli, ["check-local", "--verbose"])

        assert result.exit_code == 0
        assert "- model1.tflite" in result.output

    @patch("birdnetpi.cli.asset_installer.FilePathResolver")
    def test_check_local_missing_files(self, mock_file_resolver_class, tmp_path, runner):
        """Should report missing assets."""
        mock_resolver = MagicMock()
        mock_resolver.get_models_dir.return_value = str(tmp_path / "models")
        mock_resolver.get_ioc_database_path.return_value = str(tmp_path / "data" / "ioc_db.sqlite")
        mock_resolver.get_data_dir.return_value = str(tmp_path / "data")
        mock_file_resolver_class.return_value = mock_resolver

        result = runner.invoke(cli, ["check-local"])

        assert result.exit_code == 0
        assert "✗ Models: Not installed" in result.output
        assert "✗ IOC Database: Not installed" in result.output
        assert "✗ Avibase Database: Not installed" in result.output
        assert "✗ PatLevin Database: Not installed" in result.output
        assert "Expected location:" in result.output


class TestMainFunction:
    """Test the main entry point."""

    @patch("birdnetpi.cli.asset_installer.cli")
    def test_main_function(self, mock_cli):
        """Should call CLI with proper arguments."""
        from birdnetpi.cli.asset_installer import main

        main()

        mock_cli.assert_called_once_with(obj={})

    def test_script_entry_point(self):
        """Test module can be run as script."""
        import subprocess

        module_path = (
            Path(__file__).parent.parent.parent / "src" / "birdnetpi" / "cli" / "asset_installer.py"
        )

        # Try to run with --help to avoid actual execution
        result = subprocess.run(
            [sys.executable, str(module_path), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Should show help text
        assert result.returncode == 0
        assert "BirdNET-Pi Asset Installer" in result.stdout
