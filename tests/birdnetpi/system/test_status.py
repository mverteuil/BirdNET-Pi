"""Tests for SystemInspector class."""

import asyncio
import re
import subprocess
import time
from datetime import datetime
from unittest.mock import MagicMock, create_autospec, patch

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

    @pytest.mark.parametrize(
        "usage_percent,expected_status,expected_message_contains",
        [
            pytest.param(
                95, HealthStatus.CRITICAL, "Disk usage critical: 95.0%", id="critical_high_usage"
            ),
            pytest.param(
                85, HealthStatus.WARNING, "Disk usage warning: 85.0%", id="warning_moderate_usage"
            ),
            pytest.param(
                50, HealthStatus.HEALTHY, "Disk usage normal: 50.0%", id="healthy_low_usage"
            ),
        ],
    )
    @patch("birdnetpi.system.status.shutil.disk_usage", autospec=True)
    def test_get_disk_health(
        self, mock_disk_usage, usage_percent, expected_status, expected_message_contains
    ):
        """Should return appropriate health status based on disk usage."""
        used = usage_percent * 10
        free = 1000 - used
        mock_disk_usage.return_value = (1000, used, free)

        status, message = SystemInspector.get_disk_health()

        assert status == expected_status
        assert expected_message_contains in message


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

    @pytest.mark.parametrize(
        "cpu_percent,expected_status,expected_message_contains",
        [
            pytest.param(
                95.0, HealthStatus.CRITICAL, "CPU usage critical: 95.0%", id="critical_high_cpu"
            ),
            pytest.param(
                85.0, HealthStatus.WARNING, "CPU usage warning: 85.0%", id="warning_moderate_cpu"
            ),
            pytest.param(
                30.0, HealthStatus.HEALTHY, "CPU usage normal: 30.0%", id="healthy_normal_cpu"
            ),
        ],
    )
    @patch("birdnetpi.system.status.psutil.cpu_percent", autospec=True)
    def test_get_cpu_health(
        self, mock_cpu_percent, cpu_percent, expected_status, expected_message_contains
    ):
        """Should return appropriate health status based on CPU usage."""
        mock_cpu_percent.return_value = cpu_percent
        status, message = SystemInspector.get_cpu_health()

        assert status == expected_status
        assert expected_message_contains in message


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

    @pytest.mark.parametrize(
        "memory_percent,memory_used,expected_status,expected_message_pattern",
        [
            pytest.param(
                95.0,
                7600000000,
                HealthStatus.CRITICAL,
                r"Memory usage critical: 95\.0%.*7247MB",
                id="critical_high_memory",
            ),
            pytest.param(
                85.0,
                6800000000,
                HealthStatus.WARNING,
                r"Memory usage warning: 85\.0%",
                id="warning_moderate_memory",
            ),
            pytest.param(
                40.0,
                3200000000,
                HealthStatus.HEALTHY,
                r"Memory usage normal: 40\.0%",
                id="healthy_normal_memory",
            ),
        ],
    )
    @patch("birdnetpi.system.status.psutil.virtual_memory", autospec=True)
    def test_get_memory_health(
        self,
        mock_virtual_memory,
        memory_percent,
        memory_used,
        expected_status,
        expected_message_pattern,
    ):
        """Should return appropriate health status based on memory usage."""
        mock_virtual_memory.return_value.percent = memory_percent
        mock_virtual_memory.return_value.used = memory_used

        status, message = SystemInspector.get_memory_health()

        assert status == expected_status
        assert re.search(expected_message_pattern, message) is not None


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
            mock_run.return_value = MagicMock(spec=subprocess.CompletedProcess)
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

    @pytest.mark.parametrize(
        "temperature,expected_status,expected_message_contains",
        [
            pytest.param(
                85.0,
                HealthStatus.CRITICAL,
                "CPU temperature critical: 85.0°C",
                id="critical_high_temp",
            ),
            pytest.param(
                75.0,
                HealthStatus.WARNING,
                "CPU temperature warning: 75.0°C",
                id="warning_moderate_temp",
            ),
            pytest.param(
                45.0,
                HealthStatus.HEALTHY,
                "CPU temperature normal: 45.0°C",
                id="healthy_normal_temp",
            ),
            pytest.param(
                None,
                HealthStatus.UNKNOWN,
                "Temperature monitoring not available",
                id="unknown_no_sensor",
            ),
        ],
    )
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_temperature", autospec=True)
    def test_get_temperature_health(
        self, mock_get_temp, temperature, expected_status, expected_message_contains
    ):
        """Should return appropriate health status based on CPU temperature."""
        mock_get_temp.return_value = temperature
        status, message = SystemInspector.get_temperature_health()

        assert status == expected_status
        assert expected_message_contains in message


class TestAudioDeviceMethods:
    """Test audio device checking methods."""

    @pytest.mark.parametrize(
        "returncode,stderr,side_effect,expected_working,expected_message_contains",
        [
            pytest.param(
                0,
                None,
                None,
                True,
                "Audio input device working normally",
                id="success_device_works",
            ),
            pytest.param(
                1, b"No such device", None, False, "No such device", id="failure_no_device"
            ),
            pytest.param(
                None,
                None,
                subprocess.TimeoutExpired("arecord", 5),
                False,
                "Audio device check timed out",
                id="timeout_check_failed",
            ),
            pytest.param(
                None,
                None,
                FileNotFoundError(),
                False,
                "arecord command not found",
                id="command_not_found",
            ),
        ],
    )
    def test_check_audio_device_sync(
        self, returncode, stderr, side_effect, expected_working, expected_message_contains
    ):
        """Should handle various audio device check scenarios."""
        with patch("birdnetpi.system.status.subprocess.run", autospec=True) as mock_run:
            if side_effect:
                mock_run.side_effect = side_effect
            else:
                mock_run.return_value.returncode = returncode
                mock_run.return_value.stderr = stderr

            is_working, message = SystemInspector.check_audio_device_sync()

            assert is_working == expected_working
            assert expected_message_contains in message

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

    @pytest.mark.parametrize(
        "cpu_status,memory_status,disk_status,temp_status,"
        "expected_overall,expected_alerts,has_critical,has_warning",
        [
            pytest.param(
                (HealthStatus.HEALTHY, "CPU OK"),
                (HealthStatus.HEALTHY, "Memory OK"),
                (HealthStatus.HEALTHY, "Disk OK"),
                (HealthStatus.HEALTHY, "Temp OK"),
                "healthy",
                0,
                False,
                False,
                id="all_healthy",
            ),
            pytest.param(
                (HealthStatus.WARNING, "CPU High"),
                (HealthStatus.HEALTHY, "Memory OK"),
                (HealthStatus.WARNING, "Disk High"),
                (HealthStatus.HEALTHY, "Temp OK"),
                "warning",
                2,
                False,
                True,
                id="warnings_present",
            ),
            pytest.param(
                (HealthStatus.CRITICAL, "CPU Critical"),
                (HealthStatus.WARNING, "Memory High"),
                (HealthStatus.HEALTHY, "Disk OK"),
                (HealthStatus.HEALTHY, "Temp OK"),
                "critical",
                2,
                True,
                False,
                id="critical_with_warning",
            ),
        ],
    )
    @patch("birdnetpi.system.status.SystemInspector.get_temperature_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_disk_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_memory_health", autospec=True)
    @patch("birdnetpi.system.status.SystemInspector.get_cpu_health", autospec=True)
    def test_get_health_summary(
        self,
        mock_cpu,
        mock_memory,
        mock_disk,
        mock_temp,
        cpu_status,
        memory_status,
        disk_status,
        temp_status,
        expected_overall,
        expected_alerts,
        has_critical,
        has_warning,
    ):
        """Should return appropriate health summary based on component statuses."""
        mock_cpu.return_value = cpu_status
        mock_memory.return_value = memory_status
        mock_disk.return_value = disk_status
        mock_temp.return_value = temp_status

        result = SystemInspector.get_health_summary()

        assert result["overall_status"] == expected_overall
        assert result["alert_count"] == expected_alerts

        if has_critical:
            assert "critical_count" in result
            assert result["critical_count"] == 1
        else:
            assert "critical_count" not in result

        if has_warning and expected_overall == "warning":
            assert "warning_count" in result
            assert result["warning_count"] == 2
        else:
            assert "warning_count" not in result


class TestContainerUptime:
    """Test container uptime detection in get_system_info."""

    @pytest.mark.parametrize(
        "process_side_effect,expected_boot_source",
        [
            pytest.param(None, "container", id="accessible_pid1_uses_container_time"),
            pytest.param(
                psutil.AccessDenied("Cannot access PID 1"),
                "host",
                id="inaccessible_pid1_uses_host_time",
            ),
            pytest.param(psutil.NoSuchProcess(1), "host", id="missing_pid1_uses_host_time"),
        ],
    )
    @patch("birdnetpi.system.status.psutil.Process", autospec=True)
    @patch("birdnetpi.system.status.psutil.boot_time", autospec=True)
    def test_get_system_info_boot_time_handling(
        self, mock_boot_time, mock_process_class, process_side_effect, expected_boot_source
    ):
        """Should handle various PID 1 access scenarios for boot time."""
        # Set up mock times
        host_boot_time = 1000000.0  # Host booted long ago
        container_start_time = datetime.now().timestamp() - 600  # Container started 10 minutes ago

        # Mock system boot time (host)
        mock_boot_time.return_value = host_boot_time

        if process_side_effect:
            mock_process_class.side_effect = process_side_effect
        else:
            # Mock PID 1 process (container init)
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

            # Check which boot time was used
            if expected_boot_source == "container":
                assert info["boot_time"] == container_start_time
                assert info["boot_time"] != host_boot_time
            else:
                assert info["boot_time"] == host_boot_time

            # Verify PID 1 was checked
            mock_process_class.assert_called_once_with(1)

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
