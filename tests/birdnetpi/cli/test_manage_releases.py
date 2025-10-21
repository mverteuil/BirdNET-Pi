"""Tests for release CLI."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click import BadParameter
from click.testing import CliRunner

from birdnetpi.cli.manage_releases import _normalize_version, cli
from birdnetpi.releases.release_manager import ReleaseAsset, ReleaseManager


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_release_manager():
    """Create a mock ReleaseManager."""
    mock_manager = MagicMock(spec=ReleaseManager)
    mock_manager.get_default_assets.return_value = [
        ReleaseAsset(Path("/test/models"), Path("data/models"), "BirdNET models"),
        ReleaseAsset(Path("/test/ioc.db"), Path("data/database/ioc_reference.db"), "IOC database"),
    ]
    mock_manager.create_asset_release.return_value = {
        "version": "2.0.0",
        "asset_branch": "assets-2.0.0",
        "commit_sha": "abc123",
        "assets": ["models", "ioc.db"],
    }
    mock_manager.create_github_release.return_value = {
        "tag_name": "v2.0.0",
        "release_url": "https://github.com/user/repo/releases/tag/v2.0.0",
    }
    return mock_manager


class TestVersionNormalization:
    """Test version normalization functionality."""

    def test_normalize_version_with_single_v(self):
        """Should strip single leading 'v' character."""
        assert _normalize_version("v2.2.0") == "2.2.0"

    def test_normalize_version_with_double_v(self):
        """Should strip multiple leading 'v' characters (fixes vv2.2.0 bug)."""
        assert _normalize_version("vv2.2.0") == "2.2.0"

    def test_normalize_version_with_triple_v(self):
        """Should strip any number of leading 'v' characters."""
        assert _normalize_version("vvv2.2.0") == "2.2.0"

    def test_normalize_version_without_v(self):
        """Should leave version unchanged if no leading 'v'."""
        assert _normalize_version("2.2.0") == "2.2.0"

    def test_normalize_version_with_prerelease(self):
        """Should handle prerelease versions."""
        assert _normalize_version("v2.2.0-alpha.1") == "2.2.0-alpha.1"
        assert _normalize_version("vv2.2.0-beta") == "2.2.0-beta"

    def test_normalize_version_with_build_metadata(self):
        """Should handle build metadata."""
        assert _normalize_version("v2.2.0+build.123") == "2.2.0+build.123"

    def test_normalize_version_invalid_raises_error(self):
        """Should raise BadParameter for invalid version strings."""
        with pytest.raises(BadParameter) as exc_info:
            _normalize_version("vvinvalid")
        assert "Invalid version string" in str(exc_info.value)
        assert "not a valid semantic version" in str(exc_info.value)

    def test_normalize_version_empty_after_strip_raises_error(self):
        """Should raise BadParameter when only 'v' characters provided."""
        with pytest.raises(BadParameter) as exc_info:
            _normalize_version("vvv")
        assert "Invalid version string" in str(exc_info.value)


class TestReleaseManager:
    """Test release manager CLI commands."""

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    @patch("pathlib.Path.exists", autospec=True)
    def test_create_command_with_models(
        self, mock_exists, mock_manager_class, mock_release_manager, runner, path_resolver
    ):
        """Should create release with models."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(cli, ["create", "v2.0.0", "--include-models"])
            assert result.exit_code == 0
            assert "Creating orphaned commit with release assets" in result.output
            assert "✓ Asset release created successfully!" in result.output
            assert "Version: 2.0.0" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    @patch("pathlib.Path.exists", autospec=True)
    def test_create_command_with_github_release(
        self, mock_exists, mock_manager_class, mock_release_manager, runner, path_resolver
    ):
        """Should create GitHub release when requested."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(
                cli, ["create", "v2.0.0", "--include-models", "--create-github-release"]
            )
            assert result.exit_code == 0
            assert "Creating GitHub release" in result.output
            assert "GitHub release created: v2.0.0" in result.output
            assert "Release URL: https://github.com/user/repo/releases/tag/v2.0.0" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    def test_create_command_no_assets(
        self, mock_manager_class, mock_release_manager, runner, path_resolver
    ):
        """Should fail when no assets specified."""
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(cli, ["create", "v2.0.0"])
            assert result.exit_code == 1
            assert "Error: No assets specified for release" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    @patch("pathlib.Path.exists", autospec=True)
    def test_create_command_with_output_json(
        self, mock_exists, mock_manager_class, mock_release_manager, runner, tmp_path, path_resolver
    ):
        """Should save release data to JSON when requested."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager
        output_file = tmp_path / "release.json"
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(
                cli, ["create", "v2.0.0", "--include-models", "--output-json", str(output_file)]
            )
            assert result.exit_code == 0
            assert f"Release data written to: {output_file}" in result.output
            assert output_file.exists()

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.is_file", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.stat", autospec=True)
    def test_list_assets_command(
        self,
        mock_stat,
        mock_is_dir,
        mock_is_file,
        mock_exists,
        mock_manager_class,
        mock_release_manager,
        runner,
        path_resolver,
    ):
        """Should list available assets."""
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_is_dir.return_value = False
        mock_stat.return_value = MagicMock(spec=os.stat_result, st_size=1024 * 1024 * 10)
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(cli, ["list-assets"])
            assert result.exit_code == 0
            assert "Available assets for release:" in result.output
            assert "✓" in result.output
            assert "BirdNET models" in result.output
            assert "IOC database" in result.output

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    def test_custom_assets(
        self, mock_manager_class, mock_release_manager, runner, tmp_path, path_resolver
    ):
        """Should handle custom assets."""
        asset_file = tmp_path / "custom.txt"
        asset_file.write_text("test")
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            result = runner.invoke(
                cli,
                ["create", "v2.0.0", "--custom-assets", f"{asset_file}:custom.txt:Custom asset"],
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

    @patch("birdnetpi.cli.manage_releases.ReleaseManager", autospec=True)
    @patch("pathlib.Path.exists", autospec=True)
    def test_create_command_normalizes_double_v_version(
        self, mock_exists, mock_manager_class, mock_release_manager, runner, path_resolver
    ):
        """Should normalize version with double 'v' prefix (regression test for vv2.2.0 bug)."""
        mock_exists.return_value = True
        mock_manager_class.return_value = mock_release_manager
        with patch("birdnetpi.cli.manage_releases.PathResolver", return_value=path_resolver):
            # User accidentally provides "vv2.2.0" instead of "v2.2.0"
            result = runner.invoke(cli, ["create", "vv2.2.0", "--include-models"])
            assert result.exit_code == 0
            # Should normalize to "2.2.0" not "vv2.2.0"
            assert "Version: 2.0.0" in result.output  # From mock, but shows normalization worked
            # Verify the create_asset_release was called with normalized version
            call_args = mock_release_manager.create_asset_release.call_args
            assert call_args[0][0].version == "2.2.0"
