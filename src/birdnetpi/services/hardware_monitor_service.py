"""Hardware monitoring service for field deployments.

This service monitors hardware components like microphones, GPS devices,
and system resources to provide real-time status and alert on failures.
"""

import asyncio
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, NamedTuple

import psutil

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Hardware component health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ComponentStatus(NamedTuple):
    """Status information for a hardware component."""

    name: str
    status: HealthStatus
    message: str
    last_check: datetime
    details: dict[str, Any] | None = None


class HardwareMonitorService:
    """Monitors hardware components and system resources."""

    def __init__(
        self,
        check_interval: float = 10.0,
        audio_device_check: bool = True,
        system_resource_check: bool = True,
        gps_check: bool = False,
    ) -> None:
        """Initialize hardware monitoring service.

        Args:
            check_interval: Time between hardware checks in seconds
            audio_device_check: Whether to monitor audio devices
            system_resource_check: Whether to monitor system resources
            gps_check: Whether to monitor GPS device
        """
        self.check_interval = check_interval
        self.audio_device_check = audio_device_check
        self.system_resource_check = system_resource_check
        self.gps_check = gps_check

        self.is_running = False
        self.component_status: dict[str, ComponentStatus] = {}
        self.alert_callbacks: list[callable] = []
        self._monitor_task: asyncio.Task[None] | None = None

        # Thresholds for alerts
        self.cpu_warning_threshold = 80.0  # CPU usage percentage
        self.cpu_critical_threshold = 90.0
        self.memory_warning_threshold = 80.0  # Memory usage percentage
        self.memory_critical_threshold = 90.0
        self.disk_warning_threshold = 80.0  # Disk usage percentage
        self.disk_critical_threshold = 90.0
        self.temperature_warning_threshold = 70.0  # CPU temperature (Celsius)
        self.temperature_critical_threshold = 80.0

    async def start(self) -> None:
        """Start hardware monitoring service."""
        if self.is_running:
            return

        logger.info("Starting hardware monitoring service...")
        self.is_running = True

        # Start background monitoring task
        self._monitor_task = asyncio.create_task(self._monitoring_loop())

    async def stop(self) -> None:
        """Stop hardware monitoring service."""
        if not self.is_running:
            return

        logger.info("Stopping hardware monitoring service...")
        self.is_running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def add_alert_callback(self, callback: callable) -> None:
        """Add callback function for hardware alerts.

        Args:
            callback: Function to call when hardware alerts occur
                     Signature: callback(component_name: str, status: ComponentStatus)
        """
        if callback not in self.alert_callbacks:
            self.alert_callbacks.append(callback)

    def remove_alert_callback(self, callback: callable) -> None:
        """Remove alert callback function."""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self.is_running:
            try:
                await self._check_all_components()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in hardware monitoring loop: %s", e)
                await asyncio.sleep(self.check_interval)

    async def _check_all_components(self) -> None:
        """Check status of all monitored components."""
        now = datetime.now(timezone.utc)

        # Check audio devices
        if self.audio_device_check:
            await self._check_audio_devices(now)

        # Check system resources
        if self.system_resource_check:
            await self._check_system_resources(now)

        # Check GPS device
        if self.gps_check:
            await self._check_gps_device(now)

    async def _check_audio_devices(self, check_time: datetime) -> None:
        """Check audio device availability."""
        try:
            # Check if audio recording is possible
            result = await asyncio.create_subprocess_exec(
                "arecord",
                "-d",
                "1",
                "-f",
                "S16_LE",
                "-r",
                "48000",
                "-t",
                "wav",
                "/dev/null",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                status = ComponentStatus(
                    name="audio_input",
                    status=HealthStatus.HEALTHY,
                    message="Audio input device working normally",
                    last_check=check_time,
                )
            else:
                error_msg = stderr.decode() if stderr else "Unknown audio error"
                status = ComponentStatus(
                    name="audio_input",
                    status=HealthStatus.CRITICAL,
                    message=f"Audio input device failed: {error_msg}",
                    last_check=check_time,
                )

        except Exception as e:
            status = ComponentStatus(
                name="audio_input",
                status=HealthStatus.CRITICAL,
                message=f"Audio device check failed: {e}",
                last_check=check_time,
            )

        await self._update_component_status("audio_input", status)

    async def _check_system_resources(self, check_time: datetime) -> None:
        """Check system resource usage."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_status = self._get_resource_status(
                cpu_percent, self.cpu_warning_threshold, self.cpu_critical_threshold
            )

            cpu_component = ComponentStatus(
                name="cpu",
                status=cpu_status,
                message=f"CPU usage: {cpu_percent:.1f}%",
                last_check=check_time,
                details={"usage_percent": cpu_percent},
            )
            await self._update_component_status("cpu", cpu_component)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_status = self._get_resource_status(
                memory.percent, self.memory_warning_threshold, self.memory_critical_threshold
            )

            memory_component = ComponentStatus(
                name="memory",
                status=memory_status,
                message=f"Memory usage: {memory.percent:.1f}% ({memory.used // 1024 // 1024}MB used)",
                last_check=check_time,
                details={
                    "usage_percent": memory.percent,
                    "used_mb": memory.used // 1024 // 1024,
                    "total_mb": memory.total // 1024 // 1024,
                },
            )
            await self._update_component_status("memory", memory_component)

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            disk_status = self._get_resource_status(
                disk_percent, self.disk_warning_threshold, self.disk_critical_threshold
            )

            disk_component = ComponentStatus(
                name="disk",
                status=disk_status,
                message=f"Disk usage: {disk_percent:.1f}% ({disk.used // 1024 // 1024 // 1024}GB used)",
                last_check=check_time,
                details={
                    "usage_percent": disk_percent,
                    "used_gb": disk.used // 1024 // 1024 // 1024,
                    "total_gb": disk.total // 1024 // 1024 // 1024,
                },
            )
            await self._update_component_status("disk", disk_component)

            # Temperature (if available)
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Get CPU temperature (usually 'cpu_thermal' on Raspberry Pi)
                    cpu_temp = None
                    for name, entries in temps.items():
                        if "cpu" in name.lower() or "thermal" in name.lower():
                            if entries:
                                cpu_temp = entries[0].current
                                break

                    if cpu_temp is not None:
                        temp_status = self._get_resource_status(
                            cpu_temp, self.temperature_warning_threshold, self.temperature_critical_threshold
                        )

                        temp_component = ComponentStatus(
                            name="temperature",
                            status=temp_status,
                            message=f"CPU temperature: {cpu_temp:.1f}°C",
                            last_check=check_time,
                            details={"temperature_celsius": cpu_temp},
                        )
                        await self._update_component_status("temperature", temp_component)

            except Exception:
                # Temperature monitoring not available on this system
                pass

        except Exception as e:
            logger.error("Error checking system resources: %s", e)

    async def _check_gps_device(self, check_time: datetime) -> None:
        """Check GPS device availability."""
        if not self.gps_check:
            return
            
        try:
            # Try to connect to gpsd
            result = await asyncio.create_subprocess_exec(
                "gpspipe",
                "-w",
                "-n",
                "5",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=10)

            if result.returncode == 0 and stdout:
                status = ComponentStatus(
                    name="gps",
                    status=HealthStatus.HEALTHY,
                    message="GPS device responding",
                    last_check=check_time,
                )
            else:
                error_msg = stderr.decode() if stderr else "No GPS data received"
                status = ComponentStatus(
                    name="gps",
                    status=HealthStatus.CRITICAL,
                    message=f"GPS device failed: {error_msg}",
                    last_check=check_time,
                )

        except asyncio.TimeoutError:
            status = ComponentStatus(
                name="gps",
                status=HealthStatus.CRITICAL,
                message="GPS device timeout - may be disconnected",
                last_check=check_time,
            )
        except Exception as e:
            status = ComponentStatus(
                name="gps",
                status=HealthStatus.CRITICAL,
                message=f"GPS device check failed: {e}",
                last_check=check_time,
            )

        await self._update_component_status("gps", status)

    def _get_resource_status(self, value: float, warning_threshold: float, critical_threshold: float) -> HealthStatus:
        """Get health status based on resource value and thresholds."""
        if value >= critical_threshold:
            return HealthStatus.CRITICAL
        elif value >= warning_threshold:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    async def _update_component_status(self, component_name: str, new_status: ComponentStatus) -> None:
        """Update component status and trigger alerts if needed."""
        old_status = self.component_status.get(component_name)
        self.component_status[component_name] = new_status

        # Trigger alerts if status changed to warning or critical
        if old_status is None or old_status.status != new_status.status:
            if new_status.status in (HealthStatus.WARNING, HealthStatus.CRITICAL):
                logger.warning("Hardware alert: %s - %s", component_name, new_status.message)

                # Call alert callbacks
                for callback in self.alert_callbacks:
                    try:
                        await asyncio.create_task(
                            callback(component_name, new_status)
                            if asyncio.iscoroutinefunction(callback)
                            else asyncio.get_event_loop().run_in_executor(None, callback, component_name, new_status)
                        )
                    except Exception as e:
                        logger.error("Error in hardware alert callback: %s", e)

    def get_component_status(self, component_name: str) -> ComponentStatus | None:
        """Get status for a specific component."""
        return self.component_status.get(component_name)

    def get_all_status(self) -> dict[str, ComponentStatus]:
        """Get status for all monitored components."""
        return self.component_status.copy()

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall system health summary."""
        if not self.component_status:
            return {"overall_status": "unknown", "components": {}, "alert_count": 0}

        component_summary = {}
        critical_count = 0
        warning_count = 0

        for name, status in self.component_status.items():
            component_summary[name] = {
                "status": status.status.value,
                "message": status.message,
                "last_check": status.last_check.isoformat(),
            }

            if status.status == HealthStatus.CRITICAL:
                critical_count += 1
            elif status.status == HealthStatus.WARNING:
                warning_count += 1

        # Determine overall status
        if critical_count > 0:
            overall_status = "critical"
        elif warning_count > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return {
            "overall_status": overall_status,
            "components": component_summary,
            "alert_count": critical_count + warning_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
        }