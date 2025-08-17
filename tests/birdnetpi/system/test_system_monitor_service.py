import subprocess
from unittest.mock import mock_open, patch

import pytest

from birdnetpi.system.system_monitor_service import SystemMonitorService


@pytest.fixture
def system_monitor_service():
    """SystemMonitorService instance for testing."""
    return SystemMonitorService()


@patch("birdnetpi.system.system_monitor_service.shutil.disk_usage")
def test_get_disk_usage(mock_disk_usage, system_monitor_service):
    """Should return correct disk usage information"""
    mock_disk_usage.return_value = (1000, 500, 500)  # total, used, free
    path = "/test/path"
    result = system_monitor_service.get_disk_usage(path)
    mock_disk_usage.assert_called_once_with(path)
    assert result == {"total": 1000, "used": 500, "free": 500}


@patch("birdnetpi.system.system_monitor_service.shutil.disk_usage")
def test_check_disk_space_sufficient(mock_disk_usage, system_monitor_service):
    """Should return True for sufficient disk space"""
    mock_disk_usage.return_value = (1000, 200, 800)  # 80% free
    status, message = system_monitor_service.check_disk_space("/test/path", 10)
    assert status is True
    assert "Disk space is sufficient: 80.00% free." in message


@patch("birdnetpi.system.system_monitor_service.shutil.disk_usage")
def test_check_disk_space_low(mock_disk_usage, system_monitor_service):
    """Should return False for low disk space"""
    mock_disk_usage.return_value = (1000, 950, 50)  # 5% free
    status, message = system_monitor_service.check_disk_space("/test/path", 10)
    assert status is False
    assert "Low disk space: 5.00% free, below 10% threshold." in message


@patch("birdnetpi.system.system_monitor_service.os.path.exists", return_value=True)
@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="""line1
line2
""",
)
def test_dump_logs(mock_open, mock_exists, system_monitor_service):
    """Should dump log file content when file exists"""
    result = system_monitor_service.dump_logs("/var/log/test.log")
    assert result == "line1\nline2"


@patch("birdnetpi.system.system_monitor_service.os.path.exists")
@patch("builtins.open", new_callable=mock_open)  # Add mock_open here as well
def test_dump_logs_file_not_found(
    mock_open, mock_exists, system_monitor_service
):  # Add mock_open to args
    """Should print error when log file does not exist"""
    mock_exists.return_value = False
    result = system_monitor_service.dump_logs("/var/log/nonexistent.log")
    assert result == "Error: Log file not found at /var/log/nonexistent.log"


@patch("birdnetpi.system.system_monitor_service.os.path.exists")
@patch("builtins.open", new_callable=mock_open)  # Ensure mock_open is used
def test_dump_logs_read_error(
    mock_open, mock_exists, system_monitor_service
):  # Add mock_open to args
    """Should print error when log file cannot be read"""
    mock_exists.return_value = True
    mock_open.side_effect = OSError("Permission denied")  # Corrected
    result = system_monitor_service.dump_logs("/var/log/protected.log")
    assert "Error reading log file: Permission denied" in result


@patch("birdnetpi.system.system_monitor_service.subprocess.check_output")
def test_get_extra_info(mock_check_output, system_monitor_service):
    """Should return CPU temperature and memory usage successfully"""
    mock_check_output.side_effect = [
        # vcgencmd measure_temp
        b"temp=50.0'C\n",
        # free -h
        b"              total        used        free      shared  buff/cache   available\n"
        + b"Mem:        1.0G        0.5G        0.5G        0.0G        0.0G        0.5G\n",
    ]
    info = system_monitor_service.get_extra_info()
    assert info["cpu_temperature"] == "50.0'C"
    assert "Mem:        1.0G" in info["memory_usage"]


@patch(
    "birdnetpi.system.system_monitor_service.subprocess.check_output",
    side_effect=FileNotFoundError,
)
def test_get_extra_info_vcgencmd_not_found(mock_check_output, system_monitor_service):
    """Should handle vcgencmd not found"""
    info = system_monitor_service.get_extra_info()
    assert info["cpu_temperature"] == "N/A (vcgencmd not found)"
    assert "memory_usage" in info  # Memory check should still run


@patch(
    "birdnetpi.system.system_monitor_service.subprocess.check_output",
    side_effect=subprocess.CalledProcessError(1, "cmd"),
)
def test_get_extra_info_vcgencmd_error(mock_check_output, system_monitor_service):
    """Should handle vcgencmd execution error"""
    info = system_monitor_service.get_extra_info()
    assert "Error:" in info["cpu_temperature"]
    assert "memory_usage" in info  # Memory check should still run


@patch(
    "birdnetpi.system.system_monitor_service.subprocess.check_output",
    side_effect=[b"temp=50.0'C\n", FileNotFoundError],
)
def test_get_extra_info_free_not_found(mock_check_output, system_monitor_service):
    """Should handle free command not found"""
    info = system_monitor_service.get_extra_info()
    assert info["cpu_temperature"] == "50.0'C"
    assert info["memory_usage"] == "N/A (free command not found)"


@patch(
    "birdnetpi.system.system_monitor_service.subprocess.check_output",
    side_effect=[b"temp=50.0'C\n", subprocess.CalledProcessError(1, "cmd")],
)
def test_get_extra_info_free_error(mock_check_output, system_monitor_service):
    """Should handle free command execution error"""
    info = system_monitor_service.get_extra_info()
    assert info["cpu_temperature"] == "50.0'C"
    assert "Error:" in info["memory_usage"]
