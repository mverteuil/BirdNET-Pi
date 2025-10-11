"""Test the install_assets CLI module."""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.install_assets import cli, main
from birdnetpi.releases.update_manager import UpdateManager


@pytest.fixture
def test_version_data():
    """Should version data."""
    return ["v2.1.1", "v2.1.0", "v2.0.0"]


@pytest.fixture
def test_download_result():
    """Should download result data."""
    return {
        "version": "v2.1.1",
        "downloaded_assets": [
            "models/BirdNET_GLOBAL_3K_V2.4_Model_FP32.tflite",
            "data/ioc_db.sqlite",
            "data/wikidata_reference.db",
        ],
    }


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


class TestInstallAssets:
    """Test the install command."""

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_install_assets(self, mock_update_manager_class, test_download_result, runner):
        """Should install complete asset release."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.download_release_assets.return_value = test_download_result
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["install", "v2.1.1"])
        assert result.exit_code == 0
        assert "Installing complete asset release: v2.1.1" in result.output
        assert "✓ Asset installation completed successfully!" in result.output
        assert "Version: v2.1.1" in result.output
        assert "Downloaded assets: 3" in result.output
        mock_manager.download_release_assets.assert_called_once_with(
            version="v2.1.1",
            include_models=True,
            include_ioc_db=True,
            include_wikidata_db=True,
            github_repo="mverteuil/BirdNET-Pi",
        )

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_install_assets_json_output(
        self, mock_update_manager_class, test_download_result, tmp_path, runner
    ):
        """Should save installation data to JSON when requested."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.download_release_assets.return_value = test_download_result
        mock_update_manager_class.return_value = mock_manager
        output_file = tmp_path / "install.json"
        result = runner.invoke(cli, ["install", "v2.1.1", "--output-json", str(output_file)])
        assert result.exit_code == 0
        assert f"Installation data written to: {output_file}" in result.output
        assert output_file.exists()
        json_data = json.loads(output_file.read_text())
        assert json_data == test_download_result

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_install_assets_download_error(self, mock_update_manager_class, runner):
        """Should handle download errors gracefully."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.download_release_assets.side_effect = Exception("Download failed")
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["install", "v2.1.1"])
        assert result.exit_code == 1
        assert "✗ Error installing assets: Download failed" in result.output

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_install_assets_permission_error_help(self, mock_update_manager_class, runner):
        """Should show helpful message for permission errors."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.download_release_assets.side_effect = PermissionError(
            "Permission denied: /var/lib/birdnetpi/models"
        )
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["install", "v2.1.1"])
        assert result.exit_code == 1
        assert "✗ Error installing assets:" in result.output
        assert "LOCAL DEVELOPMENT SETUP REQUIRED" in result.output
        assert "export BIRDNETPI_DATA=./data" in result.output
        assert "uv run install-assets install v2.1.1" in result.output


class TestListVersions:
    """Test the list-versions command."""

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_list_versions(self, mock_update_manager_class, test_version_data, runner):
        """Should list available asset versions."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.list_available_versions.return_value = test_version_data
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["list-versions"])
        assert result.exit_code == 0
        assert "Available asset versions:" in result.output
        assert "Latest version: v2.1.1" in result.output
        assert "• v2.1.1" in result.output
        assert "• v2.1.0" in result.output
        assert "• v2.0.0" in result.output

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_list_versions_empty(self, mock_update_manager_class, runner):
        """Should handle empty version list."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.list_available_versions.return_value = []
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["list-versions"])
        assert result.exit_code == 0
        assert "No asset versions found." in result.output

    @patch("birdnetpi.cli.install_assets.UpdateManager", autospec=True)
    def test_list_versions_error(self, mock_update_manager_class, runner):
        """Should handle listing errors gracefully."""
        mock_manager = MagicMock(spec=UpdateManager)
        mock_manager.list_available_versions.side_effect = Exception("API error")
        mock_update_manager_class.return_value = mock_manager
        result = runner.invoke(cli, ["list-versions"])
        assert result.exit_code == 1
        assert "✗ Error listing available assets: API error" in result.output


class TestCheckLocal:
    """Test the check-local command."""

    def test_check_local_assets_exist(self, tmp_path, runner, path_resolver):
        """Should report existing assets."""
        path_resolver.get_models_dir = lambda: tmp_path / "models"
        path_resolver.get_ioc_database_path = lambda: tmp_path / "data" / "ioc_db.sqlite"
        path_resolver.get_database_dir = lambda: tmp_path / "data"
        with patch("birdnetpi.cli.install_assets.PathResolver", return_value=path_resolver):
            models_dir = tmp_path / "models"
            models_dir.mkdir(parents=True)
            (models_dir / "model1.tflite").write_bytes(b"model" * 1000)
            (models_dir / "model2.tflite").write_bytes(b"model" * 2000)
            data_dir = tmp_path / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "ioc_db.sqlite").write_bytes(b"database" * 1000)
            (data_dir / "wikidata_reference.db").write_bytes(b"wikidata" * 750)
            result = runner.invoke(cli, ["check-local"])
            assert result.exit_code == 0
            assert "✓ BirdNET Models: 2 models" in result.output
            assert "✓ IOC Reference Database:" in result.output
            assert "✓ Wikidata Reference Database:" in result.output

    def test_check_local_verbose_mode(self, tmp_path, runner, path_resolver):
        """Should show detailed info in verbose mode."""
        path_resolver.get_models_dir = lambda: tmp_path / "models"
        path_resolver.get_ioc_database_path = lambda: tmp_path / "data" / "ioc_db.sqlite"
        path_resolver.get_database_dir = lambda: tmp_path / "data"
        with patch("birdnetpi.cli.install_assets.PathResolver", return_value=path_resolver):
            models_dir = tmp_path / "models"
            models_dir.mkdir(parents=True)
            (models_dir / "model1.tflite").write_bytes(b"model" * 1000)
            result = runner.invoke(cli, ["check-local", "--verbose"])
            assert result.exit_code == 0
            assert "- model1.tflite" in result.output

    def test_check_local_missing_files(self, tmp_path, runner, path_resolver):
        """Should report missing assets."""
        path_resolver.get_models_dir = lambda: tmp_path / "models"
        path_resolver.get_ioc_database_path = lambda: tmp_path / "data" / "ioc_db.sqlite"
        path_resolver.get_database_dir = lambda: tmp_path / "data"
        path_resolver.get_wikidata_database_path = (
            lambda: tmp_path / "data" / "wikidata_reference.db"
        )
        with patch("birdnetpi.cli.install_assets.PathResolver", return_value=path_resolver):
            result = runner.invoke(cli, ["check-local"])
            assert result.exit_code == 0
            assert "✗ BirdNET Models: Not installed" in result.output
            assert "✗ IOC Reference Database: Not installed" in result.output
            assert "✗ Wikidata Reference Database: Not installed" in result.output
            assert "Expected location:" in result.output


class TestMainFunction:
    """Test the main entry point."""

    @patch("birdnetpi.cli.install_assets.cli", autospec=True)
    def test_main_function(self, mock_cli):
        """Should call CLI with proper arguments."""
        main()
        mock_cli.assert_called_once_with(obj={})

    def test_script_entry_point(self, repo_root):
        """Should run module as script."""
        module_path = repo_root / "src" / "birdnetpi" / "cli" / "install_assets.py"
        result = subprocess.run(
            [sys.executable, str(module_path), "--help"], capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert "BirdNET-Pi Asset Installer" in result.stdout
