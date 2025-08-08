"""Tests for the HardwareMonitorService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.services.hardware_monitor_service import (
    ComponentStatus,
    HardwareMonitorService,
    HealthStatus,
)


@pytest.fixture
def hardware_monitor():
    """Create a HardwareMonitorService instance for testing."""
    return HardwareMonitorService(
        check_interval=0.1,  # Fast interval for testing
        audio_device_check=True,
        system_resource_check=True,
        gps_check=False,
    )


class TestHardwareMonitorService:
    """Test the HardwareMonitorService class."""

    def test_initialization(self, hardware_monitor):
        """Test that HardwareMonitorService initializes correctly."""
        service = hardware_monitor

        assert service.check_interval == 0.1
        assert service.audio_device_check is True
        assert service.system_resource_check is True
        assert service.gps_check is False
        assert service.is_running is False
        assert len(service.component_status) == 0
        assert len(service.alert_callbacks) == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, hardware_monitor):
        """Test starting and stopping the hardware monitor."""
        service = hardware_monitor

        await service.start()
        assert service.is_running is True
        assert service._monitor_task is not None

        await service.stop()
        assert service.is_running is False

    def test_add_remove_alert_callback(self, hardware_monitor):
        """Test adding and removing alert callbacks."""
        service = hardware_monitor

        def test_callback(component_name, status):
            pass

        # Add callback
        service.add_alert_callback(test_callback)
        assert test_callback in service.alert_callbacks

        # Add same callback again (should not duplicate)
        service.add_alert_callback(test_callback)
        assert len(service.alert_callbacks) == 1

        # Remove callback
        service.remove_alert_callback(test_callback)
        assert test_callback not in service.alert_callbacks

    @pytest.mark.asyncio
    async def test_check_audio_devices(self, hardware_monitor):
        """Test audio device check when audio is working."""
        service = hardware_monitor
        check_time = datetime.now(UTC)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock successful audio test
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"")
            mock_subprocess.return_value = mock_process

            await service._check_audio_devices(check_time)

            status = service.get_component_status("audio_input")
            assert status is not None
            assert status.status == HealthStatus.HEALTHY
            assert "working normally" in status.message.lower()

    @pytest.mark.asyncio
    async def test_check_audio_devices_failure(self, hardware_monitor):
        """Test audio device check when audio fails."""
        service = hardware_monitor
        check_time = datetime.now(UTC)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock failed audio test
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"Audio device error")
            mock_subprocess.return_value = mock_process

            await service._check_audio_devices(check_time)

            status = service.get_component_status("audio_input")
            assert status is not None
            assert status.status == HealthStatus.CRITICAL
            assert "failed" in status.message.lower()

    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @pytest.mark.asyncio
    async def test_check_system_resources(self, mock_disk, mock_memory, mock_cpu, hardware_monitor):
        """Test system resource monitoring."""
        service = hardware_monitor
        check_time = datetime.now(UTC)

        # Mock system resource data
        mock_cpu.return_value = 50.0
        mock_memory.return_value = MagicMock(percent=60.0, used=1024**3, total=2 * (1024**3))
        mock_disk.return_value = MagicMock(used=10 * (1024**3), total=100 * (1024**3))

        await service._check_system_resources(check_time)

        # Check CPU status
        cpu_status = service.get_component_status("cpu")
        assert cpu_status is not None
        assert cpu_status.status == HealthStatus.HEALTHY
        assert "50.0%" in cpu_status.message

        # Check memory status
        memory_status = service.get_component_status("memory")
        assert memory_status is not None
        assert memory_status.status == HealthStatus.HEALTHY
        assert "60.0%" in memory_status.message

        # Check disk status
        disk_status = service.get_component_status("disk")
        assert disk_status is not None
        assert disk_status.status == HealthStatus.HEALTHY
        assert "10.0%" in disk_status.message

    @patch("psutil.cpu_percent")
    @pytest.mark.asyncio
    async def test_check_system_resources_high_cpu(self, mock_cpu, hardware_monitor):
        """Test system resource monitoring with high CPU usage."""
        service = hardware_monitor
        check_time = datetime.now(UTC)

        # Mock high CPU usage
        mock_cpu.return_value = 95.0

        with patch("psutil.virtual_memory") as mock_memory, patch("psutil.disk_usage") as mock_disk:
            mock_memory.return_value = MagicMock(percent=30.0, used=512**3, total=2 * (1024**3))
            mock_disk.return_value = MagicMock(used=10 * (1024**3), total=100 * (1024**3))

            await service._check_system_resources(check_time)

            cpu_status = service.get_component_status("cpu")
            assert cpu_status is not None
            assert cpu_status.status == HealthStatus.CRITICAL
            assert "95.0%" in cpu_status.message

    def test_get_resource_status(self, hardware_monitor):
        """Test resource status determination based on thresholds."""
        service = hardware_monitor

        # Test healthy status
        status = service._get_resource_status(50.0, 80.0, 90.0)
        assert status == HealthStatus.HEALTHY

        # Test warning status
        status = service._get_resource_status(85.0, 80.0, 90.0)
        assert status == HealthStatus.WARNING

        # Test critical status
        status = service._get_resource_status(95.0, 80.0, 90.0)
        assert status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_update_component_status__alerts(self, hardware_monitor):
        """Test component status updates and alert triggering."""
        service = hardware_monitor
        alert_called = False
        alert_component = None
        alert_status = None

        async def test_callback(component_name, status):
            nonlocal alert_called, alert_component, alert_status
            alert_called = True
            alert_component = component_name
            alert_status = status

        service.add_alert_callback(test_callback)

        # Create a critical status update
        critical_status = ComponentStatus(
            name="test_component",
            status=HealthStatus.CRITICAL,
            message="Test critical error",
            last_check=datetime.now(UTC),
        )

        await service._update_component_status("test_component", critical_status)

        # Check that alert was triggered
        assert alert_called is True
        assert alert_component == "test_component"
        assert alert_status.status == HealthStatus.CRITICAL  # type: ignore[union-attr]

    def test_get_component_status(self, hardware_monitor):
        """Test getting component status."""
        service = hardware_monitor

        # Test non-existent component
        status = service.get_component_status("nonexistent")
        assert status is None

        # Add a component status
        test_status = ComponentStatus(
            name="test_component",
            status=HealthStatus.HEALTHY,
            message="Test message",
            last_check=datetime.now(UTC),
        )
        service.component_status["test_component"] = test_status

        # Test existing component
        status = service.get_component_status("test_component")
        assert status is not None
        assert status.name == "test_component"
        assert status.status == HealthStatus.HEALTHY

    def test_get_all_status(self, hardware_monitor):
        """Test getting all component statuses."""
        service = hardware_monitor

        # Empty status
        all_status = service.get_all_status()
        assert len(all_status) == 0

        # Add some statuses
        status1 = ComponentStatus("comp1", HealthStatus.HEALTHY, "OK", datetime.now(UTC))
        status2 = ComponentStatus("comp2", HealthStatus.WARNING, "Warning", datetime.now(UTC))

        service.component_status["comp1"] = status1
        service.component_status["comp2"] = status2

        all_status = service.get_all_status()
        assert len(all_status) == 2
        assert "comp1" in all_status
        assert "comp2" in all_status

    def test_get_health_summary_empty(self, hardware_monitor):
        """Test health summary when no components are monitored."""
        service = hardware_monitor

        summary = service.get_health_summary()
        assert summary["overall_status"] == "unknown"
        assert len(summary["components"]) == 0
        assert summary["alert_count"] == 0

    def test_get_health_summary__components(self, hardware_monitor):
        """Test health summary with various component statuses."""
        service = hardware_monitor

        # Add various component statuses
        now = datetime.now(UTC)
        service.component_status["healthy_comp"] = ComponentStatus(
            "healthy_comp", HealthStatus.HEALTHY, "OK", now
        )
        service.component_status["warning_comp"] = ComponentStatus(
            "warning_comp", HealthStatus.WARNING, "Warning", now
        )
        service.component_status["critical_comp"] = ComponentStatus(
            "critical_comp", HealthStatus.CRITICAL, "Critical", now
        )

        summary = service.get_health_summary()
        assert summary["overall_status"] == "critical"  # Worst case determines overall
        assert len(summary["components"]) == 3
        assert summary["alert_count"] == 2  # Warning + Critical
        assert summary["critical_count"] == 1
        assert summary["warning_count"] == 1

        # Test summary with only warnings
        service.component_status.pop("critical_comp")
        summary = service.get_health_summary()
        assert summary["overall_status"] == "warning"
        assert summary["alert_count"] == 1

        # Test summary with only healthy
        service.component_status.pop("warning_comp")
        summary = service.get_health_summary()
        assert summary["overall_status"] == "healthy"
        assert summary["alert_count"] == 0

    @pytest.mark.asyncio
    async def test_gps_check_disabled(self, hardware_monitor):
        """Test GPS check when GPS monitoring is disabled."""
        service = hardware_monitor
        service.gps_check = False
        check_time = datetime.now(UTC)

        await service._check_gps_device(check_time)

        # GPS status should not be set when GPS check is disabled
        gps_status = service.get_component_status("gps")
        assert gps_status is None

    @pytest.mark.asyncio
    async def test_alert_callback__exception_handling(self, hardware_monitor):
        """Test that exceptions in alert callbacks don't break the service."""
        service = hardware_monitor

        def failing_callback(component_name, status):
            raise Exception("Test callback error")

        service.add_alert_callback(failing_callback)

        # Create a critical status update
        critical_status = ComponentStatus(
            name="test_component",
            status=HealthStatus.CRITICAL,
            message="Test critical error",
            last_check=datetime.now(UTC),
        )

        # This should not raise an exception despite the failing callback
        await service._update_component_status("test_component", critical_status)

        # Status should still be updated
        status = service.get_component_status("test_component")
        assert status is not None
        assert status.status == HealthStatus.CRITICAL
