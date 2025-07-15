from unittest.mock import patch

import pytest

from birdnetpi.managers.update_manager import UpdateManager


@pytest.fixture
def update_manager(tmp_path):
    """Provide an UpdateManager instance for testing."""
    return UpdateManager()


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_update_birdnet_success(mock_run, update_manager):
    """Should update BirdNET successfully."""
    update_manager.update_birdnet()
    assert mock_run.call_count == 12


@patch("birdnetpi.managers.update_manager.subprocess.run")
def test_update_caddyfile_success(mock_run, update_manager):
    """Should update the Caddyfile successfully."""
    update_manager.update_caddyfile("test_url", "test_path")
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
