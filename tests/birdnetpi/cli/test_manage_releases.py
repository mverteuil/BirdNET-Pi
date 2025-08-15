"""Tests for release CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.manage_releases import cli
from birdnetpi.managers.release_manager import ReleaseAsset


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_release_manager():
    """Create a mock ReleaseManager."""
    mock_manager = MagicMock()
    mock_manager.get_default_assets.return_value = [
        ReleaseAsset(Path("/test/models"), Path("data/models"), "BirdNET models"),
        ReleaseAsset(Path("/test/ioc.db"), Path("data/database/ioc_reference.db"), "IOC database"),
    ]
    mock_manager.create_asset_release.return_value = {
        "version": "v2.0.0",
        "asset_branch": "assets-v2.0.0",
        "commit_sha": "abc123",
        "assets": ["models", "ioc.db"],
    }
    mock_manager.create_github_release.return_value = {
        "tag_name": "v2.0.0",
        "release_url": "https://github.com/user/repo/releases/tag/v2.0.0",
    }
    return mock_manager


class TestReleaseManager:
    """Test release manager CLI commands."""

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    @patch("pathlib.Path.exists")
    def test_create_command_with_models(
        self, mock_exists, mock_resolver_class, mock_manager_class, mock_release_manager, runner
    ):
        """Should create release with models."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager

        result = runner.invoke(cli, ["create", "v2.0.0", "--include-models"])

        assert result.exit_code == 0
        assert "Creating orphaned commit with release assets" in result.output
        assert "✓ Asset release created successfully!" in result.output
        assert "Version: v2.0.0" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    @patch("pathlib.Path.exists")
    def test_create_command_with_github_release(
        self, mock_exists, mock_resolver_class, mock_manager_class, mock_release_manager, runner
    ):
        """Should create GitHub release when requested."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager

        result = runner.invoke(
            cli, ["create", "v2.0.0", "--include-models", "--create-github-release"]
        )

        assert result.exit_code == 0
        assert "Creating GitHub release" in result.output
        assert "GitHub release created: v2.0.0" in result.output
        assert "Release URL: https://github.com/user/repo/releases/tag/v2.0.0" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    def test_create_command_no_assets(
        self, mock_resolver_class, mock_manager_class, mock_release_manager, runner
    ):
        """Should fail when no assets specified."""
        mock_manager_class.return_value = mock_release_manager

        result = runner.invoke(cli, ["create", "v2.0.0"])

        assert result.exit_code == 1
        assert "Error: No assets specified for release" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    @patch("pathlib.Path.exists")
    def test_create_command_with_output_json(
        self,
        mock_exists,
        mock_resolver_class,
        mock_manager_class,
        mock_release_manager,
        runner,
        tmp_path,
    ):
        """Should save release data to JSON when requested."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager

        output_file = tmp_path / "release.json"

        result = runner.invoke(
            cli,
            ["create", "v2.0.0", "--include-models", "--output-json", str(output_file)],
        )

        assert result.exit_code == 0
        assert f"Release data written to: {output_file}" in result.output
        assert output_file.exists()

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.is_file")
    @patch("pathlib.Path.is_dir")
    @patch("pathlib.Path.stat")
    def test_list_assets_command(
        self,
        mock_stat,
        mock_is_dir,
        mock_is_file,
        mock_exists,
        mock_resolver_class,
        mock_manager_class,
        mock_release_manager,
        runner,
    ):
        """Should list available assets."""
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_is_dir.return_value = False
        mock_stat.return_value = MagicMock(st_size=1024 * 1024 * 10)  # 10 MB
        mock_manager_class.return_value = mock_release_manager

        result = runner.invoke(cli, ["list-assets"])

        assert result.exit_code == 0
        assert "Available assets for release:" in result.output
        assert "✓" in result.output  # Asset exists
        assert "BirdNET models" in result.output
        assert "IOC database" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager")
    @patch("birdnetpi.cli.manage_releases.PathResolver")
    def test_custom_assets(
        self,
        mock_resolver_class,
        mock_manager_class,
        mock_release_manager,
        runner,
        tmp_path,
    ):
        """Should handle custom assets."""
        # Create test asset file
        asset_file = tmp_path / "custom.txt"
        asset_file.write_text("test")

        mock_manager_class.return_value = mock_release_manager

        result = runner.invoke(
            cli,
            [
                "create",
                "v2.0.0",
                "--custom-assets",
                f"{asset_file}:custom.txt:Custom asset",
            ],
        )

        assert result.exit_code == 0
        assert "✓ Asset release created successfully!" in result.output

    def test_main_help(self, runner):
        """Should show help text."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "BirdNET-Pi Release Management" in result.output
        assert "create" in result.output
        assert "list-assets" in result.output
