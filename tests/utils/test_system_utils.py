from unittest.mock import patch

import pytest

from birdnetpi.utils.system_utils import SystemUtils


@pytest.fixture
def system_utils():
    """Provide a SystemUtils instance for testing."""
    return SystemUtils()


@patch("birdnetpi.utils.system_utils.open")
@patch("birdnetpi.utils.system_utils.subprocess.run")
def test_get_system_timezone_from_etc_timezone(mock_run, mock_open, system_utils):
    """Should return the timezone from /etc/timezone."""
    mock_open.return_value.__enter__.return_value.read.return_value = "America/New_York"
    timezone = system_utils.get_system_timezone()
    assert timezone == "America/New_York"
    mock_run.assert_not_called()


@patch("birdnetpi.utils.system_utils.open", side_effect=FileNotFoundError)
@patch("birdnetpi.utils.system_utils.subprocess.run")
def test_get_system_timezone_from_timedatectl(mock_run, mock_open, system_utils):
    """Should return the timezone from timedatectl."""
    mock_run.return_value.stdout = "Timezone=Europe/London"
    timezone = system_utils.get_system_timezone()
    assert timezone == "Europe/London"


@patch("birdnetpi.utils.system_utils.open", side_effect=FileNotFoundError)
@patch("birdnetpi.utils.system_utils.subprocess.run", side_effect=Exception)
def test_get_system_timezone_fallback_to_utc(mock_run, mock_open, system_utils):
    """Should return UTC if all other methods fail."""
    timezone = system_utils.get_system_timezone()
    assert timezone == "UTC"
