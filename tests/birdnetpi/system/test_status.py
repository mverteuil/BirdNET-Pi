"""Tests for SystemInspector class."""

import asyncio
import subprocess
import time
from datetime import datetime
from unittest.mock import create_autospec, patch

import psutil
import pytest

from birdnetpi.system.status import HealthStatus, SystemInspector


class TestDiskMethods:
    """Test disk-related inspection methods."""

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_usage(self, mock_disk_usage):
        """Should return correct disk usage information."""
        mock_disk_usage.return_value = (1000, 500, 500)  # total, used, free
        result = SystemInspector.get_disk_usage("/test/path")

        mock_disk_usage.assert_called_once_with("/test/path")
        assert result == {"total": 1000, "used": 500, "free": 500, "percent": 50.0}

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_usage_default_path(self, mock_disk_usage):
        """Should use root path by default."""
        mock_disk_usage.return_value = (2000, 1000, 1000)
        result = SystemInspector.get_disk_usage()

        mock_disk_usage.assert_called_once_with("/")
        assert result["percent"] == 50.0

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_check_disk_space_sufficient(self, mock_disk_usage):
        """Should return True for sufficient disk space."""
        mock_disk_usage.return_value = (1000, 200, 800)  # 80% free
        status, message = SystemInspector.check_disk_space("/test/path", 10)

        assert status is True
        assert "Disk space is sufficient: 80.00% free" in message

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_check_disk_space_low(self, mock_disk_usage):
        """Should return False for low disk space."""
        mock_disk_usage.return_value = (1000, 950, 50)  # 5% free
        status, message = SystemInspector.check_disk_space("/test/path", 10)

        assert status is False
        assert "Low disk space: 5.00% free, below 10% threshold" in message

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_health_critical(self, mock_disk_usage):
        """Should return CRITICAL status for high disk usage."""
        mock_disk_usage.return_value = (1000, 950, 50)  # 95% used
        status, message = SystemInspector.get_disk_health()

        assert status == HealthStatus.CRITICAL
        assert "Disk usage critical: 95.0%" in message

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_health_warning(self, mock_disk_usage):
        """Should return WARNING status for moderate disk usage."""
        mock_disk_usage.return_value = (1000, 850, 150)  # 85% used
        status, message = SystemInspector.get_disk_health()

        assert status == HealthStatus.WARNING
        assert "Disk usage warning: 85.0%" in message

    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_health_healthy(self, mock_disk_usage):
        """Should return HEALTHY status for low disk usage."""
        mock_disk_usage.return_value = (1000, 500, 500)  # 50% used
        status, message = SystemInspector.get_disk_health()

        assert status == HealthStatus.HEALTHY
        assert "Disk usage normal: 50.0%" in message


class TestCPUMethods:
    """Test CPU-related inspection methods."""

    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_usage(self, mock_cpu_percent):
        """Should return CPU usage percentage."""
        mock_cpu_percent.return_value = 45.5
        result = SystemInspector.get_cpu_usage()

        mock_cpu_percent.assert_called_once_with(interval=1.0)
        assert result == 45.5

    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_usage_custom_interval(self, mock_cpu_percent):
        """Should accept custom interval for CPU measurement."""
        mock_cpu_percent.return_value = 30.0
        result = SystemInspector.get_cpu_usage(interval=2.5)

        mock_cpu_percent.assert_called_once_with(interval=2.5)
        assert result == 30.0

    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_health_critical(self, mock_cpu_percent):
        """Should return CRITICAL status for high CPU usage."""
        mock_cpu_percent.return_value = 95.0
        status, message = SystemInspector.get_cpu_health()

        assert status == HealthStatus.CRITICAL
        assert "CPU usage critical: 95.0%" in message

    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_health_warning(self, mock_cpu_percent):
        """Should return WARNING status for moderate CPU usage."""
        mock_cpu_percent.return_value = 85.0
        status, message = SystemInspector.get_cpu_health()

        assert status == HealthStatus.WARNING
        assert "CPU usage warning: 85.0%" in message

    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_health_healthy(self, mock_cpu_percent):
        """Should return HEALTHY status for normal CPU usage."""
        mock_cpu_percent.return_value = 30.0
        status, message = SystemInspector.get_cpu_health()

        assert status == HealthStatus.HEALTHY
        assert "CPU usage normal: 30.0%" in message


class TestMemoryMethods:
    """Test memory-related inspection methods."""

    @patch("birdnetpi.system.status.psutil.virtual_memory", autospec=True)
    def test_get_memory_usage(self, mock_virtual_memory):
        """Should return memory usage statistics."""
        # mock_virtual_memory is already autospec'd, just configure its return_value
        mock_virtual_memory.return_value.total = 8000000000  # 8GB
        mock_virtual_memory.return_value.used = 4000000000  # 4GB
        mock_virtual_memory.return_value.available = 3500000000  # 3.5GB
        mock_virtual_memory.return_value.percent = 50.0

        result = SystemInspector.get_memory_usage()

        assert result == {
            "total": 8000000000,
            "used": 4000000000,
            "free": 3500000000,
            "percent": 50.0,
        }

    @patch("birdnetpi.system.status.psutil.virtual_memory", autospec=True)
    def test_get_memory_health_critical(self, mock_virtual_memory):
        """Should return CRITICAL status for high memory usage."""
        mock_virtual_memory.return_value.percent = 95.0
        mock_virtual_memory.return_value.used = 7600000000

        status, message = SystemInspector.get_memory_health()

        assert status == HealthStatus.CRITICAL
        assert "Memory usage critical: 95.0%" in message
        assert "7247MB" in message  # 7600000000 / 1024 / 1024

    @patch("birdnetpi.system.status.psutil.virtual_memory", autospec=True)
    def test_get_memory_health_warning(self, mock_virtual_memory):
        """Should return WARNING status for moderate memory usage."""
        mock_virtual_memory.return_value.percent = 85.0
        mock_virtual_memory.return_value.used = 6800000000

        status, message = SystemInspector.get_memory_health()

        assert status == HealthStatus.WARNING
        assert "Memory usage warning: 85.0%" in message

    @patch("birdnetpi.system.status.psutil.virtual_memory", autospec=True)
    def test_get_memory_health_healthy(self, mock_virtual_memory):
        """Should return HEALTHY status for normal memory usage."""
        mock_virtual_memory.return_value.percent = 40.0
        mock_virtual_memory.return_value.used = 3200000000

        status, message = SystemInspector.get_memory_health()

        assert status == HealthStatus.HEALTHY
        assert "Memory usage normal: 40.0%" in message


class TestTemperatureMethods:
    """Test temperature-related inspection methods."""

    def test_get_cpu_temperature_from_psutil(self):
        """Should get temperature from psutil sensors."""
        # Create a mock sensor entry with the current attribute
        mock_entry = create_autospec(
            type(
                "SensorEntry", (), {"label": "", "current": 0.0, "high": None, "critical": None}
            )(),
            spec_set=True,
        )
        mock_entry.current = 45.5

        with patch.object(psutil, "sensors_temperatures", create=True) as mock_sensors:
            mock_sensors.return_value = {"cpu_thermal": [mock_entry]}
            result = SystemInspector.get_cpu_temperature()
            assert result == 45.5

    @patch("birdnetpi.system.status.subprocess.run", autospec=True)
    def test_get_cpu_temperature_from_vcgencmd(self, mock_run):
        """Should fallback to vcgencmd when psutil fails."""
        with patch.object(psutil, "sensors_temperatures", create=True) as mock_sensors:
            mock_sensors.side_effect = AttributeError()
            mock_run.return_value = create_autospec(
                subprocess.CompletedProcess, spec_set=True, args=[]
            )
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "temp=42.8'C\n"

            result = SystemInspector.get_cpu_temperature()
            assert result == 42.8

    @patch("birdnetpi.system.status.subprocess.run", autospec=True)
    def test_get_cpu_temperature_none(self, mock_run):
        """Should return None when temperature unavailable."""
        with patch.object(psutil, "sensors_temperatures", create=True) as mock_sensors:
            mock_sensors.side_effect = AttributeError()
            mock_run.side_effect = FileNotFoundError()

            result = SystemInspector.get_cpu_temperature()
            assert result is None

    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    def test_get_temperature_health_critical(self, mock_get_temp):
        """Should return CRITICAL status for high temperature."""
        mock_get_temp.return_value = 85.0
        status, message = SystemInspector.get_temperature_health()

        assert status == HealthStatus.CRITICAL
        assert "CPU temperature critical: 85.0°C" in message

    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    def test_get_temperature_health_warning(self, mock_get_temp):
        """Should return WARNING status for moderate temperature."""
        mock_get_temp.return_value = 75.0
        status, message = SystemInspector.get_temperature_health()

        assert status == HealthStatus.WARNING
        assert "CPU temperature warning: 75.0°C" in message

    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    def test_get_temperature_health_healthy(self, mock_get_temp):
        """Should return HEALTHY status for normal temperature."""
        mock_get_temp.return_value = 45.0
        status, message = SystemInspector.get_temperature_health()

        assert status == HealthStatus.HEALTHY
        assert "CPU temperature normal: 45.0°C" in message

    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    def test_get_temperature_health_unknown(self, mock_get_temp):
        """Should return UNKNOWN status when temperature unavailable."""
        mock_get_temp.return_value = None
        status, message = SystemInspector.get_temperature_health()

        assert status == HealthStatus.UNKNOWN
        assert "Temperature monitoring not available" in message


class TestAudioDeviceMethods:
    """Test audio device checking methods."""

    def test_check_audio_device_sync_success(self):
        """Should return success when audio device works."""
        with patch("birdnetpi.system.status.subprocess.run", autospec=True) as mock_run:
            mock_run.return_value = create_autospec(
                subprocess.CompletedProcess, spec_set=True, args=[]
            )
            mock_run.return_value.returncode = 0

            is_working, message = SystemInspector.check_audio_device_sync()

            assert is_working is True
            assert "Audio input device working normally" in message

    def test_check_audio_device_sync_failure(self):
        """Should return failure when audio device fails."""
        with patch("birdnetpi.system.status.subprocess.run", autospec=True) as mock_run:
            mock_run.return_value = create_autospec(
                subprocess.CompletedProcess, spec_set=True, args=[]
            )
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = b"No such device"

            is_working, message = SystemInspector.check_audio_device_sync()

            assert is_working is False
            assert "Audio input device failed" in message
            assert "No such device" in message

    def test_check_audio_device_sync_timeout(self):
        """Should handle timeout when checking audio device."""
        with patch("birdnetpi.system.status.subprocess.run", autospec=True) as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("arecord", 5)

            is_working, message = SystemInspector.check_audio_device_sync()

            assert is_working is False
            assert "Audio device check timed out" in message

    def test_check_audio_device_sync_not_found(self):
        """Should handle missing arecord command."""
        with patch("birdnetpi.system.status.subprocess.run", autospec=True) as mock_run:
            mock_run.side_effect = FileNotFoundError()

            is_working, message = SystemInspector.check_audio_device_sync()

            assert is_working is False
            assert "arecord command not found" in message

    @pytest.mark.asyncio
    async def test_check_audio_device_async_success(self):
        """Should return success when audio device works (async)."""
        with patch(
            "birdnetpi.system.status.asyncio.create_subprocess_exec", autospec=True
        ) as mock_exec:
            # Create a properly spec'd asyncio.subprocess.Process mock
            mock_process = create_autospec(asyncio.subprocess.Process, spec_set=True)
            mock_process.returncode = 0

            async def mock_communicate():
                return None, None

            mock_process.communicate = mock_communicate
            mock_exec.return_value = mock_process

            is_working, message = await SystemInspector.check_audio_device()

            assert is_working is True
            assert "Audio input device working normally" in message


class TestSystemInfoMethods:
    """Test system information gathering methods."""

    @patch("birdnetpi.system.status.psutil.net_if_addrs", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_disk_usage", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_memory_usage", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_usage", autospec=True)
    @patch("birdnetpi.system.status.psutil.Process", autospec=True)
    @patch("birdnetpi.system.status.psutil.boot_time", autospec=True)
    @patch("birdnetpi.system.status.psutil.cpu_count", autospec=True)
    def test_get_system_info(
        self,
        mock_cpu_count,
        mock_boot_time,
        mock_process_class,
        mock_cpu_usage,
        mock_memory,
        mock_disk,
        mock_temp,
        mock_net_if,
    ):
        """Should gather comprehensive system information."""
        mock_cpu_count.return_value = 4
        mock_boot_time.return_value = 1234567890

        # Mock PID 1 as not accessible (typical in non-container environment)
        mock_process_class.side_effect = psutil.AccessDenied("Cannot access PID 1")

        mock_cpu_usage.return_value = 25.0
        mock_memory.return_value = {"percent": 50.0}
        mock_disk.return_value = {"percent": 60.0}
        mock_temp.return_value = 45.5
        mock_net_if.return_value = {"eth0": [], "wlan0": []}

        result = SystemInspector.get_system_info()

        assert result["cpu_count"] == 4
        assert result["boot_time"] == 1234567890  # Falls back to boot_time
        assert result["cpu_percent"] == 25.0
        assert result["memory"]["percent"] == 50.0
        assert result["disk"]["percent"] == 60.0
        assert result["cpu_temperature"] == 45.5
        assert "eth0" in result["network_interfaces"]
        assert "wlan0" in result["network_interfaces"]

    @patch("birdnetpi.system.status.SystemInspector.get_temperature_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_disk_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_memory_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_health", autospec=True)
    def test_get_health_summary_all_healthy(self, mock_cpu, mock_memory, mock_disk, mock_temp):
        """Should return healthy summary when all components healthy."""
        mock_cpu.return_value = (HealthStatus.HEALTHY, "CPU OK")
        mock_memory.return_value = (HealthStatus.HEALTHY, "Memory OK")
        mock_disk.return_value = (HealthStatus.HEALTHY, "Disk OK")
        mock_temp.return_value = (HealthStatus.HEALTHY, "Temp OK")

        result = SystemInspector.get_health_summary()

        assert result["overall_status"] == "healthy"
        assert result["alert_count"] == 0
        assert "critical_count" not in result
        assert "warning_count" not in result

    @patch("birdnetpi.system.status.SystemInspector.get_temperature_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_disk_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_memory_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_health", autospec=True)
    def test_get_health_summary_with_warnings(self, mock_cpu, mock_memory, mock_disk, mock_temp):
        """Should return warning summary when components have warnings."""
        mock_cpu.return_value = (HealthStatus.WARNING, "CPU High")
        mock_memory.return_value = (HealthStatus.HEALTHY, "Memory OK")
        mock_disk.return_value = (HealthStatus.WARNING, "Disk High")
        mock_temp.return_value = (HealthStatus.HEALTHY, "Temp OK")

        result = SystemInspector.get_health_summary()

        assert result["overall_status"] == "warning"
        assert result["alert_count"] == 2
        assert result["warning_count"] == 2
        assert "critical_count" not in result

    @patch("birdnetpi.system.status.SystemInspector.get_temperature_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_disk_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_memory_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_health", autospec=True)
    def test_get_health_summary_with_critical(self, mock_cpu, mock_memory, mock_disk, mock_temp):
        """Should return critical summary when any component is critical."""
        mock_cpu.return_value = (HealthStatus.CRITICAL, "CPU Critical")
        mock_memory.return_value = (HealthStatus.WARNING, "Memory High")
        mock_disk.return_value = (HealthStatus.HEALTHY, "Disk OK")
        mock_temp.return_value = (HealthStatus.HEALTHY, "Temp OK")

        result = SystemInspector.get_health_summary()

        assert result["overall_status"] == "critical"
        assert result["alert_count"] == 2
        assert result["critical_count"] == 1
        assert "warning_count" not in result  # Only shown for warning status


class TestContainerUptime:
    """Test container uptime detection in get_system_info."""

    @patch("birdnetpi.system.status.psutil.Process", autospec=True)
    @patch("birdnetpi.system.status.psutil.boot_time", autospec=True)
    def test_get_system_info_uses_container_init_time(self, mock_boot_time, mock_process_class):
        """Should use PID 1's create time in a container environment."""
        # Set up mock times
        host_boot_time = 1000000.0  # Host booted long ago
        container_start_time = datetime.now().timestamp() - 600  # Container started 10 minutes ago

        # Mock system boot time (host)
        mock_boot_time.return_value = host_boot_time

        # Mock PID 1 process (container init)
        # mock_process_class is already autospec'd, just configure its return_value
        mock_process_class.return_value.create_time.return_value = container_start_time

        # Mock other dependencies for get_system_info
        with (
            patch("birdnetpi.system.status.psutil.cpu_count", return_value=4),
            patch.object(SystemInspector, "get_cpu_usage", return_value=25.0),
            patch.object(SystemInspector, "get_memory_usage", return_value={"percent": 50.0}),
            patch.object(SystemInspector, "get_disk_usage", return_value={"percent": 60.0}),
            patch.object(SystemInspector, "get_cpu_temperature", return_value=None),
            patch("birdnetpi.system.status.psutil.net_if_addrs", return_value={}),
        ):
            # Get system info
            info = SystemInspector.get_system_info()

            # Should have used container's PID 1 create time, not host boot time
            assert info["boot_time"] == container_start_time
            assert info["boot_time"] != host_boot_time

            # Verify PID 1 was checked
            mock_process_class.assert_called_once_with(1)

    @patch("birdnetpi.system.status.psutil.Process", autospec=True)
    @patch("birdnetpi.system.status.psutil.boot_time", autospec=True)
    def test_get_system_info_fallback_to_host_when_pid1_inaccessible(
        self, mock_boot_time, mock_process_class
    ):
        """Should fall back to host boot time if PID 1 is not accessible."""
        host_boot_time = 1000000.0

        # Mock system boot time
        mock_boot_time.return_value = host_boot_time

        # Mock PID 1 access denied (common in some environments)
        mock_process_class.side_effect = psutil.AccessDenied("Cannot access PID 1")

        # Mock other dependencies
        with (
            patch("birdnetpi.system.status.psutil.cpu_count", return_value=4),
            patch.object(SystemInspector, "get_cpu_usage", return_value=25.0),
            patch.object(SystemInspector, "get_memory_usage", return_value={"percent": 50.0}),
            patch.object(SystemInspector, "get_disk_usage", return_value={"percent": 60.0}),
            patch.object(SystemInspector, "get_cpu_temperature", return_value=None),
            patch("birdnetpi.system.status.psutil.net_if_addrs", return_value={}),
        ):
            # Get system info
            info = SystemInspector.get_system_info()

            # Should have fallen back to host boot time
            assert info["boot_time"] == host_boot_time

    @patch("birdnetpi.system.status.psutil.Process", autospec=True)
    @patch("birdnetpi.system.status.psutil.boot_time", autospec=True)
    def test_get_system_info_fallback_when_pid1_doesnt_exist(
        self, mock_boot_time, mock_process_class
    ):
        """Should fall back to host boot time if PID 1 doesn't exist."""
        host_boot_time = 1000000.0

        # Mock system boot time
        mock_boot_time.return_value = host_boot_time

        # Mock PID 1 doesn't exist (shouldn't happen but be defensive)
        mock_process_class.side_effect = psutil.NoSuchProcess(1)

        # Mock other dependencies
        with (
            patch("birdnetpi.system.status.psutil.cpu_count", return_value=4),
            patch.object(SystemInspector, "get_cpu_usage", return_value=25.0),
            patch.object(SystemInspector, "get_memory_usage", return_value={"percent": 50.0}),
            patch.object(SystemInspector, "get_disk_usage", return_value={"percent": 60.0}),
            patch.object(SystemInspector, "get_cpu_temperature", return_value=None),
            patch("birdnetpi.system.status.psutil.net_if_addrs", return_value={}),
        ):
            # Get system info
            info = SystemInspector.get_system_info()

            # Should have fallen back to host boot time
            assert info["boot_time"] == host_boot_time

    def test_uptime_calculation_from_boot_time(self):
        """Should calculate uptime correctly with container boot time."""
        # Create a mock boot time 10 minutes ago
        ten_minutes_ago = time.time() - 600

        # Calculate uptime in seconds
        uptime_seconds = time.time() - ten_minutes_ago

        # Should be approximately 600 seconds (10 minutes)
        assert 595 <= uptime_seconds <= 605  # Allow small variance

        # Calculate uptime in days
        uptime_days = int(uptime_seconds // 86400)

        # Should be 0 days (less than a day)
        assert uptime_days == 0

        # Test with a boot time 2.5 days ago
        two_and_half_days_ago = time.time() - (2.5 * 86400)
        uptime_seconds = time.time() - two_and_half_days_ago
        uptime_days = int(uptime_seconds // 86400)

        # Should be 2 days (integer division)
        assert uptime_days == 2
