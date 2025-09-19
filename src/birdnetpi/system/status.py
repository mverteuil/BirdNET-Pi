"""System status inspection utilities.

This module provides static methods for inspecting system health and resource usage.
Consolidates functionality from the former hardware_monitor_manager and system_monitor_service.
"""

import asyncio
import platform
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

import psutil


class HealthStatus(Enum):
    """System component health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class DiskUsage(TypedDict):
    """Disk usage statistics."""

    total: int
    used: int
    free: int
    percent: float


class MemoryUsage(TypedDict):
    """Memory usage statistics."""

    total: int
    used: int
    free: int
    percent: float


class SystemInspector:
    """Static utilities for inspecting system status and health.

    Provides methods for checking:
    - Disk usage and space
    - CPU usage and temperature
    - Memory usage
    - Audio device availability
    - GPS device availability
    """

    # Default thresholds for resource alerts
    CPU_WARNING_THRESHOLD = 80.0
    CPU_CRITICAL_THRESHOLD = 90.0
    MEMORY_WARNING_THRESHOLD = 80.0
    MEMORY_CRITICAL_THRESHOLD = 90.0
    DISK_WARNING_THRESHOLD = 80.0
    DISK_CRITICAL_THRESHOLD = 90.0
    TEMPERATURE_WARNING_THRESHOLD = 70.0
    TEMPERATURE_CRITICAL_THRESHOLD = 80.0

    @staticmethod
    def get_disk_usage(path: str = "/") -> DiskUsage:
        """Get disk usage statistics for a given path.

        Args:
            path: Path to check disk usage for (default: root)

        Returns:
            Dictionary with total, used, free bytes and percentage used
        """
        total, used, free = shutil.disk_usage(path)
        percent = (used / total) * 100 if total > 0 else 0
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        }

    @staticmethod
    def check_disk_space(path: str = "/", threshold_percent: int = 10) -> tuple[bool, str]:
        """Check if free disk space is below a specified threshold.

        Args:
            path: Path to check disk space for
            threshold_percent: Minimum free space percentage required

        Returns:
            Tuple of (is_ok, message) indicating if space is sufficient
        """
        usage = SystemInspector.get_disk_usage(path)
        free_percent = 100 - usage["percent"]

        if free_percent < threshold_percent:
            return (
                False,
                f"Low disk space: {free_percent:.2f}% free, below {threshold_percent}% threshold.",
            )
        return True, f"Disk space is sufficient: {free_percent:.2f}% free."

    @staticmethod
    def get_disk_health(path: str = "/") -> tuple[HealthStatus, str]:
        """Get disk health status based on usage thresholds.

        Args:
            path: Path to check disk health for

        Returns:
            Tuple of (health_status, message)
        """
        usage = SystemInspector.get_disk_usage(path)
        percent = usage["percent"]

        if percent >= SystemInspector.DISK_CRITICAL_THRESHOLD:
            return HealthStatus.CRITICAL, f"Disk usage critical: {percent:.1f}%"
        elif percent >= SystemInspector.DISK_WARNING_THRESHOLD:
            return HealthStatus.WARNING, f"Disk usage warning: {percent:.1f}%"
        else:
            return HealthStatus.HEALTHY, f"Disk usage normal: {percent:.1f}%"

    @staticmethod
    def get_cpu_usage(interval: float = 1.0) -> float:
        """Get current CPU usage percentage.

        Args:
            interval: Time in seconds to measure CPU usage

        Returns:
            CPU usage percentage (0-100)
        """
        return psutil.cpu_percent(interval=interval)

    @staticmethod
    def get_cpu_health() -> tuple[HealthStatus, str]:
        """Get CPU health status based on usage thresholds.

        Returns:
            Tuple of (health_status, message)
        """
        cpu_percent = SystemInspector.get_cpu_usage()

        if cpu_percent >= SystemInspector.CPU_CRITICAL_THRESHOLD:
            return HealthStatus.CRITICAL, f"CPU usage critical: {cpu_percent:.1f}%"
        elif cpu_percent >= SystemInspector.CPU_WARNING_THRESHOLD:
            return HealthStatus.WARNING, f"CPU usage warning: {cpu_percent:.1f}%"
        else:
            return HealthStatus.HEALTHY, f"CPU usage normal: {cpu_percent:.1f}%"

    @staticmethod
    def get_memory_usage() -> MemoryUsage:
        """Get current memory usage statistics.

        Returns:
            Dictionary with total, used, free bytes and percentage used
        """
        memory = psutil.virtual_memory()
        return {
            "total": memory.total,
            "used": memory.used,
            "free": memory.available,
            "percent": memory.percent,
        }

    @staticmethod
    def get_memory_health() -> tuple[HealthStatus, str]:
        """Get memory health status based on usage thresholds.

        Returns:
            Tuple of (health_status, message)
        """
        memory = SystemInspector.get_memory_usage()
        percent = memory["percent"]
        used_mb = memory["used"] // 1024 // 1024

        if percent >= SystemInspector.MEMORY_CRITICAL_THRESHOLD:
            return HealthStatus.CRITICAL, f"Memory usage critical: {percent:.1f}% ({used_mb}MB)"
        elif percent >= SystemInspector.MEMORY_WARNING_THRESHOLD:
            return HealthStatus.WARNING, f"Memory usage warning: {percent:.1f}% ({used_mb}MB)"
        else:
            return HealthStatus.HEALTHY, f"Memory usage normal: {percent:.1f}% ({used_mb}MB)"

    @staticmethod
    def get_cpu_temperature() -> float | None:
        """Get CPU temperature if available.

        Returns:
            Temperature in Celsius or None if not available
        """
        # Try psutil first (more portable)
        try:
            temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            if temps:
                # Look for CPU temperature
                for name, entries in temps.items():
                    if "cpu" in name.lower() or "thermal" in name.lower():
                        if entries:
                            return entries[0].current
        except (AttributeError, Exception):
            pass

        # Fallback to Raspberry Pi specific vcgencmd
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse output like "temp=42.8'C"
                temp_str = result.stdout.strip().split("=")[1].replace("'C", "")
                return float(temp_str)
        except (FileNotFoundError, ValueError, subprocess.SubprocessError):
            pass

        return None

    @staticmethod
    def get_temperature_health() -> tuple[HealthStatus, str]:
        """Get temperature health status based on thresholds.

        Returns:
            Tuple of (health_status, message)
        """
        temp = SystemInspector.get_cpu_temperature()

        if temp is None:
            return HealthStatus.UNKNOWN, "Temperature monitoring not available"

        if temp >= SystemInspector.TEMPERATURE_CRITICAL_THRESHOLD:
            return HealthStatus.CRITICAL, f"CPU temperature critical: {temp:.1f}°C"
        elif temp >= SystemInspector.TEMPERATURE_WARNING_THRESHOLD:
            return HealthStatus.WARNING, f"CPU temperature warning: {temp:.1f}°C"
        else:
            return HealthStatus.HEALTHY, f"CPU temperature normal: {temp:.1f}°C"

    @staticmethod
    async def check_audio_device() -> tuple[bool, str]:
        """Check if audio input device is available.

        Returns:
            Tuple of (is_working, message)
        """
        try:
            # Test audio recording capability
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
            _, stderr = await asyncio.wait_for(result.communicate(), timeout=5)

            if result.returncode == 0:
                return True, "Audio input device working normally"
            else:
                error_msg = stderr.decode() if stderr else "Unknown audio error"
                return False, f"Audio input device failed: {error_msg}"

        except TimeoutError:
            return False, "Audio device check timed out"
        except FileNotFoundError:
            return False, "arecord command not found - audio subsystem may not be installed"
        except Exception as e:
            return False, f"Audio device check failed: {e}"

    @staticmethod
    def check_audio_device_sync() -> tuple[bool, str]:
        """Check audio device synchronously.

        Returns:
            Tuple of (is_working, message)
        """
        try:
            result = subprocess.run(
                ["arecord", "-d", "1", "-f", "S16_LE", "-r", "48000", "-t", "wav", "/dev/null"],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                return True, "Audio input device working normally"
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown audio error"
                return False, f"Audio input device failed: {error_msg}"

        except subprocess.TimeoutExpired:
            return False, "Audio device check timed out"
        except FileNotFoundError:
            return False, "arecord command not found - audio subsystem may not be installed"
        except Exception as e:
            return False, f"Audio device check failed: {e}"

    @staticmethod
    async def check_gps_device() -> tuple[bool, str]:
        """Check if GPS device is available via gpsd.

        Returns:
            Tuple of (is_working, message)
        """
        try:
            # Try to get data from gpsd
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
                return True, "GPS device responding"
            else:
                error_msg = stderr.decode() if stderr else "No GPS data received"
                return False, f"GPS device failed: {error_msg}"

        except TimeoutError:
            return False, "GPS device timeout - may be disconnected"
        except FileNotFoundError:
            return False, "gpspipe command not found - gpsd may not be installed"
        except Exception as e:
            return False, f"GPS device check failed: {e}"

    @staticmethod
    def _check_docker_environment() -> bool:
        """Check if running in a Docker container."""
        return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()

    @staticmethod
    def _get_raspberry_pi_model() -> str | None:
        """Try to detect Raspberry Pi model from device tree."""
        try:
            with open("/proc/device-tree/model") as f:
                model = f.read().strip().replace("\x00", "")
                if model:
                    # Clean up the model string
                    if "raspberry pi" in model.lower():
                        # Extract important part: "Raspberry Pi 4 Model B" -> "Raspberry Pi 4"
                        parts = model.split()
                        if len(parts) >= 3:
                            return f"{parts[0]} {parts[1]} {parts[2]}"
                    return model
        except (FileNotFoundError, PermissionError):
            return None

    @staticmethod
    def _get_macos_model() -> str:
        """Get macOS hardware model name."""
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.model"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                model = result.stdout.strip()
                # Convert Mac model identifiers to friendly names
                mac_models = {
                    "MacBookPro": "MacBook Pro",
                    "MacBookAir": "MacBook Air",
                    "iMac": "iMac",
                    "Mac": "Mac",
                }
                for key, value in mac_models.items():
                    if key in model:
                        return value
                return model
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return "macOS"

    @staticmethod
    def _get_linux_type() -> str:
        """Get specific Linux device type based on architecture."""
        machine = platform.machine()
        if machine in ["x86_64", "amd64"]:
            return "Linux PC"
        elif machine.startswith("arm") or machine == "aarch64":
            return "ARM Linux"
        return "Linux"

    @staticmethod
    def get_device_name() -> str:
        """Get a descriptive name for the current device/platform.

        Returns:
            Device name string (e.g., "Raspberry Pi 4", "Docker Container", "MacBook Pro")
        """
        # Check if running in Docker
        if SystemInspector._check_docker_environment():
            return "Docker Container"

        # Try to detect Raspberry Pi model
        rpi_model = SystemInspector._get_raspberry_pi_model()
        if rpi_model:
            return rpi_model

        system = platform.system()

        # Platform-specific detection
        if system == "Darwin":
            return SystemInspector._get_macos_model()
        elif system == "Linux":
            return SystemInspector._get_linux_type()
        elif system == "Windows":
            return "Windows PC"

        # Generic fallback
        return system

    @staticmethod
    def get_system_info() -> dict[str, Any]:
        """Get comprehensive system information.

        Returns:
            Dictionary containing various system metrics and info
        """
        info: dict[str, Any] = {}

        # Basic system info
        info["cpu_count"] = psutil.cpu_count()

        # Get container or system boot time
        # In a container, use process 1's create time (container's init process)
        # Otherwise fall back to system boot time
        try:
            # In a container, PID 1 is the container's init process
            container_process = psutil.Process(1)
            info["boot_time"] = container_process.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Fall back to system boot time if we can't access PID 1
            info["boot_time"] = psutil.boot_time()

        info["device_name"] = SystemInspector.get_device_name()
        info["platform"] = platform.platform()

        # Resource usage
        info["cpu_percent"] = SystemInspector.get_cpu_usage()
        info["memory"] = SystemInspector.get_memory_usage()
        info["disk"] = SystemInspector.get_disk_usage()

        # Temperature if available
        temp = SystemInspector.get_cpu_temperature()
        if temp is not None:
            info["cpu_temperature"] = temp

        # Network interfaces
        try:
            net_if = psutil.net_if_addrs()
            info["network_interfaces"] = list(net_if.keys())
        except Exception:
            info["network_interfaces"] = []

        return info

    @staticmethod
    def get_health_summary() -> dict[str, Any]:
        """Get overall system health summary.

        Returns:
            Dictionary with health status for all monitored components
        """
        summary: dict[str, Any] = {
            "components": {},
            "overall_status": HealthStatus.HEALTHY.value,
        }

        # Check each component
        cpu_status, cpu_msg = SystemInspector.get_cpu_health()
        summary["components"]["cpu"] = {
            "status": cpu_status.value,
            "message": cpu_msg,
        }

        memory_status, memory_msg = SystemInspector.get_memory_health()
        summary["components"]["memory"] = {
            "status": memory_status.value,
            "message": memory_msg,
        }

        disk_status, disk_msg = SystemInspector.get_disk_health()
        summary["components"]["disk"] = {
            "status": disk_status.value,
            "message": disk_msg,
        }

        temp_status, temp_msg = SystemInspector.get_temperature_health()
        summary["components"]["temperature"] = {
            "status": temp_status.value,
            "message": temp_msg,
        }

        # Determine overall status
        critical_count = sum(
            1 for c in summary["components"].values() if c["status"] == HealthStatus.CRITICAL.value
        )
        warning_count = sum(
            1 for c in summary["components"].values() if c["status"] == HealthStatus.WARNING.value
        )

        if critical_count > 0:
            summary["overall_status"] = HealthStatus.CRITICAL.value
            summary["critical_count"] = critical_count
        elif warning_count > 0:
            summary["overall_status"] = HealthStatus.WARNING.value
            summary["warning_count"] = warning_count

        summary["alert_count"] = critical_count + warning_count

        return summary
