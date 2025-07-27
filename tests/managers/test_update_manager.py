from unittest.mock import patch

import pytest

from birdnetpi.managers.update_manager import UpdateManager
from birdnetpi.models.caddy_config import CaddyConfig
from birdnetpi.models.git_update_config import GitUpdateConfig


@pytest.fixture
def update_manager(tmp_path):
    """Provide an UpdateManager instance for testing."""
    manager = UpdateManager()
    manager.repo_path = str(tmp_path)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # Create dummy script files for testing the symlink loop
    for i in range(6):
        (scripts_dir / f"script{i}.sh").touch()
    return manager


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_update_birdnet_success(mock_run, update_manager):
    """Should update BirdNET successfully."""
    config = GitUpdateConfig()
    update_manager.update_birdnet(config)
    assert mock_run.call_count == 12


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_update_caddyfile_success(mock_run, update_manager):
    """Should update the Caddyfile successfully."""
    config = CaddyConfig(birdnetpi_url="test_url")
    update_manager.update_caddyfile(config)
    assert mock_run.call_count == 4


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_get_commits_behind_success(mock_run, update_manager):
    """Should return the number of commits behind."""
    mock_run.return_value.stdout = (
        "Your branch is behind 'origin/main' by 3 commits, and can be fast-forwarded."
    )
    commits_behind = update_manager.get_commits_behind()
    assert commits_behind == 3


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_get_commits_behind_diverged(mock_run, update_manager):
    """Should return the number of commits behind when diverged."""
    mock_run.return_value.stdout = (
        "Your branch and 'origin/main' have diverged, and have 1 and 2 different "
        "commits each, respectively."
    )
    commits_behind = update_manager.get_commits_behind()
    assert commits_behind == 3


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_get_commits_behind_up_to_date(mock_run, update_manager):
    """Should return 0 when the branch is up to date."""
    mock_run.return_value.stdout = "Your branch is up to date with 'origin/main'."
    commits_behind = update_manager.get_commits_behind()
    assert commits_behind == 0


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_get_commits_behind_error(mock_run, update_manager):
    """Should return -1 when there is an error."""
    mock_run.side_effect = Exception
    commits_behind = update_manager.get_commits_behind()
    assert commits_behind == -1
