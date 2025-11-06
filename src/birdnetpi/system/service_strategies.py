import abc
import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ServiceManagementStrategy(abc.ABC):
    """Abstract Base Class for service management strategies.

    Defines the interface for different service management implementations
    (e.g., systemd, supervisord).
    """

    @abc.abstractmethod
    def start_service(self, service_name: str) -> None:
        """Start a specified system service."""
        pass

    @abc.abstractmethod
    def stop_service(self, service_name: str) -> None:
        """Stop a specified system service."""
        pass

    @abc.abstractmethod
    def restart_service(self, service_name: str) -> None:
        """Restarts a specified system service."""
        pass

    @abc.abstractmethod
    def enable_service(self, service_name: str) -> None:
        """Enable a specified system service to start on boot."""
        pass

    @abc.abstractmethod
    def disable_service(self, service_name: str) -> None:
        """Disables a specified system service from starting on boot."""
        pass

    @abc.abstractmethod
    def get_service_status(self, service_name: str) -> str:
        """Return the status of a specified system service."""
        pass

    @abc.abstractmethod
    def daemon_reload(self) -> None:
        """Reload daemon configuration (if applicable)."""
        pass

    @abc.abstractmethod
    def get_service_details(self, service_name: str) -> dict[str, Any]:
        """Get detailed status including uptime for a service.

        Returns:
            Dictionary with status, pid, uptime_seconds, start_time, etc.
        """
        pass

    @abc.abstractmethod
    def get_system_uptime(self) -> float:
        """Get system/container uptime in seconds."""
        pass

    @abc.abstractmethod
    def reboot_system(self) -> bool:
        """Reboot the system/container if supported.

        Returns:
            True if reboot initiated, False if not supported.
        """
        pass


class EmbeddedSystemdStrategy(ServiceManagementStrategy):
    """Service management strategy for systems using systemd (e.g., Raspberry Pi OS)."""

    def _run_systemctl_command(self, action: str, service_name: str = "") -> None:
        """Run a systemctl command with optional service name."""
        try:
            cmd = ["sudo", "systemctl", action]
            if service_name:
                cmd.append(service_name)
            subprocess.run(cmd, check=True)
            if service_name:
                logger.info(f"Service {service_name} {action}ed successfully.")
            else:
                logger.info(f"Systemctl {action} completed successfully.")
        except subprocess.CalledProcessError as e:
            if service_name:
                logger.error(f"Error {action}ing service {service_name}: {e}")
            else:
                logger.error(f"Error running systemctl {action}: {e}")
        except FileNotFoundError:
            logger.error("Error: systemctl command not found. Is systemd installed?")

    def start_service(self, service_name: str) -> None:
        """Start a specified system service."""
        self._run_systemctl_command("start", service_name)

    def stop_service(self, service_name: str) -> None:
        """Stop a specified system service."""
        self._run_systemctl_command("stop", service_name)

    def restart_service(self, service_name: str) -> None:
        """Restart a specified system service."""
        self._run_systemctl_command("restart", service_name)

    def enable_service(self, service_name: str) -> None:
        """Enable a specified system service to start on boot."""
        self._run_systemctl_command("enable", service_name)

    def disable_service(self, service_name: str) -> None:
        """Disable a specified system service from starting on boot."""
        self._run_systemctl_command("disable", service_name)

    def get_service_status(self, service_name: str) -> str:
        """Return the status of a specified system service."""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return "active"
            elif result.returncode == 3:
                return "inactive"
            else:
                return "unknown"
        except FileNotFoundError:
            logger.error("Error: systemctl command not found. Is systemd installed?")
            return "error"

    def daemon_reload(self) -> None:
        """Reload systemd daemon configuration."""
        self._run_systemctl_command("daemon-reload")

    def _parse_systemd_timestamp(self, timestamp_value: str) -> tuple[float | None, str | None]:
        """Parse systemd timestamp and return uptime_seconds and start_time."""
        if not timestamp_value or timestamp_value == "n/a":
            return None, None

        try:
            # Example format: "Wed 2024-01-15 10:30:45 UTC"
            # Remove timezone info and parse
            timestamp_str = " ".join(timestamp_value.split()[:-1])
            start_time = datetime.strptime(timestamp_str, "%a %Y-%m-%d %H:%M:%S")
            uptime = datetime.now() - start_time
            return uptime.total_seconds(), start_time.isoformat()
        except (ValueError, IndexError):
            return None, None

    def _parse_systemctl_output(self, output: str, details: dict[str, Any]) -> None:
        """Parse systemctl show output and update details dict."""
        for line in output.splitlines():
            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            if key == "ActiveState":
                details["status"] = "active" if value == "active" else "inactive"
            elif key == "MainPID":
                details["pid"] = int(value) if value and value != "0" else None
            elif key == "ActiveEnterTimestamp" and value:
                uptime_seconds, start_time = self._parse_systemd_timestamp(value)
                if uptime_seconds is not None:
                    details["uptime_seconds"] = uptime_seconds
                    details["start_time"] = start_time
            elif key == "SubState":
                details["sub_state"] = value

    def get_service_details(self, service_name: str) -> dict[str, Any]:
        """Get detailed status including uptime for a service."""
        try:
            # Get detailed service info using systemctl show
            result = subprocess.run(
                ["sudo", "systemctl", "show", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )

            details = {
                "name": service_name,
                "status": "unknown",
                "pid": None,
                "uptime_seconds": None,
            }

            if result.returncode == 0:
                self._parse_systemctl_output(result.stdout, details)

            return details

        except Exception as e:
            logger.error(f"Error getting service details for {service_name}: {e}")
            return {"name": service_name, "status": "error", "pid": None, "uptime_seconds": None}

    def get_system_uptime(self) -> float:
        """Get system uptime in seconds from /proc/uptime."""
        try:
            from pathlib import Path

            uptime_path = Path("/proc/uptime")
            if uptime_path.exists():
                uptime_content = uptime_path.read_text()
                return float(uptime_content.split()[0])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting system uptime: {e}")
            return 0.0

    def reboot_system(self) -> bool:
        """Reboot the system using systemctl."""
        try:
            subprocess.run(["sudo", "systemctl", "reboot"], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to reboot system: {e}")
            return False
        except FileNotFoundError:
            logger.error("systemctl command not found")
            return False


class DockerSupervisordStrategy(ServiceManagementStrategy):
    """Service management strategy for Docker containers using Supervisord."""

    def _run_supervisorctl_command(self, action: str, service_name: str = "") -> None:
        """Run a supervisorctl command with optional service name."""
        try:
            cmd = ["supervisorctl", action]
            if service_name:
                cmd.append(service_name)
            subprocess.run(cmd, check=True)
            if service_name:
                logger.info(f"Service {service_name} {action}ed successfully via supervisorctl.")
            else:
                logger.info(f"Supervisorctl {action} completed successfully.")
        except subprocess.CalledProcessError as e:
            if service_name:
                logger.error(f"Error {action}ing service {service_name} via supervisorctl: {e}")
            else:
                logger.error(f"Error running supervisorctl {action}: {e}")
        except FileNotFoundError:
            logger.error(
                "Error: supervisorctl command not found. Is Supervisord installed and configured?"
            )

    def start_service(self, service_name: str) -> None:
        """Start a specified system service."""
        self._run_supervisorctl_command("start", service_name)

    def stop_service(self, service_name: str) -> None:
        """Stop a specified system service."""
        self._run_supervisorctl_command("stop", service_name)

    def restart_service(self, service_name: str) -> None:
        """Restart a specified system service."""
        self._run_supervisorctl_command("restart", service_name)

    def enable_service(self, service_name: str) -> None:
        """Enable a specified system service to start on boot."""
        logger.info(
            "Enabling service "
            f"{service_name} is not directly supported by supervisorctl in the "
            "same way as systemd. Supervisor manages processes based on its "
            "configuration."
        )

    def disable_service(self, service_name: str) -> None:
        """Disable a specified system service from starting on boot."""
        logger.info(
            "Disabling service "
            f"{service_name} is not directly supported by supervisorctl in the "
            "same way as systemd. To disable, remove it from Supervisor's "
            "configuration."
        )

    def get_service_status(self, service_name: str) -> str:
        """Return the status of a specified system service."""
        try:
            result = subprocess.run(
                ["supervisorctl", "status", service_name],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip()
            if "RUNNING" in output:
                return "active"
            elif "STOPPED" in output:
                return "inactive"
            else:
                return "unknown"
        except FileNotFoundError:
            logger.error("Error: supervisorctl command not found. Is Supervisor installed?")
            return "error"

    def daemon_reload(self) -> None:
        """Reload supervisord configuration (reread and update)."""
        # Reread the configuration files
        self._run_supervisorctl_command("reread", "")
        # Update to apply any changes
        self._run_supervisorctl_command("update", "")

    def _parse_supervisor_uptime(self, uptime_str: str) -> float | None:
        """Parse supervisor uptime string to seconds."""
        # Parse format like "0:45:30" or "2:15:45:30" (days:hours:minutes:seconds)
        parts = uptime_str.split(":")
        try:
            if len(parts) == 3:  # HH:MM:SS
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 4:  # DD:HH:MM:SS
                days, hours, minutes, seconds = map(int, parts)
                return days * 86400 + hours * 3600 + minutes * 60 + seconds
        except ValueError:
            pass
        return None

    def _parse_supervisor_status(self, output: str, details: dict[str, Any]) -> None:
        """Parse supervisorctl status output and update details dict."""
        # Example: "service_name     RUNNING   pid 1234, uptime 0:45:30"
        if "RUNNING" in output:
            details["status"] = "active"

            # Extract PID
            pid_match = re.search(r"pid (\d+)", output)
            if pid_match:
                details["pid"] = int(pid_match.group(1))

            # Extract uptime
            uptime_match = re.search(r"uptime ([\d:]+)", output)
            if uptime_match:
                uptime_seconds = self._parse_supervisor_uptime(uptime_match.group(1))
                if uptime_seconds is not None:
                    details["uptime_seconds"] = uptime_seconds
        elif "STOPPED" in output:
            details["status"] = "inactive"
        elif "STARTING" in output:
            details["status"] = "starting"
        elif "FATAL" in output:
            details["status"] = "failed"

    def get_service_details(self, service_name: str) -> dict[str, Any]:
        """Get detailed status including uptime for a service from supervisorctl."""
        try:
            result = subprocess.run(
                ["supervisorctl", "status", service_name],
                capture_output=True,
                text=True,
                check=False,
            )

            details = {
                "name": service_name,
                "status": "unknown",
                "pid": None,
                "uptime_seconds": None,
            }

            if result.returncode == 0:
                self._parse_supervisor_status(result.stdout.strip(), details)

            return details

        except Exception as e:
            logger.error(f"Error getting service details for {service_name}: {e}")
            return {"name": service_name, "status": "error", "pid": None, "uptime_seconds": None}

    def get_system_uptime(self) -> float:
        """Get container uptime in seconds.

        In Docker, /proc/uptime shows the host system uptime, not container uptime.
        We need to get the actual container start time.
        """
        try:
            # Use the modification time of /proc/1 to get container start time
            import time
            from pathlib import Path

            proc_1_path = Path("/proc/1")
            if proc_1_path.exists():
                container_start_time = proc_1_path.stat().st_mtime
                current_time = time.time()
                uptime_seconds = current_time - container_start_time

                # Sanity check - if uptime is negative or unreasonably large, fall back
                if 0 <= uptime_seconds <= 365 * 24 * 3600:  # Less than a year
                    return uptime_seconds

            # Fallback to /proc/uptime if the above doesn't work
            uptime_path = Path("/proc/uptime")
            if uptime_path.exists():
                uptime_content = uptime_path.read_text()
                return float(uptime_content.split()[0])

            return 0.0

        except Exception as e:
            logger.error(f"Error getting container uptime: {e}")
            return 0.0

    def reboot_system(self) -> bool:
        """Attempt to reboot the Docker container.

        This will only work if the container is running with appropriate privileges
        and the init system supports it.
        """
        try:
            # First check if we're running as PID 1 (init process)
            with open("/proc/1/cmdline") as f:
                cmdline = f.read()

            # Try different reboot methods
            # Method 1: If supervisord is PID 1, we can try to signal it
            if "supervisord" in cmdline:
                try:
                    # Send TERM signal to PID 1 which should trigger container restart
                    subprocess.run(["kill", "-TERM", "1"], check=True)
                    return True
                except Exception:
                    pass

            # Method 2: Try reboot command if available
            try:
                subprocess.run(["reboot"], check=True)
                return True
            except FileNotFoundError:
                pass

            # Method 3: Try to exit the container cleanly
            # This will cause Docker to restart it if --restart policy is set
            try:
                subprocess.run(["supervisorctl", "shutdown"], check=True)
                return True
            except Exception:
                pass

            logger.warning("Container reboot not supported in this configuration")
            return False

        except Exception as e:
            logger.error(f"Failed to reboot container: {e}")
            return False


class ServiceStrategySelector:
    """Selects the appropriate service management strategy based on the environment."""

    @staticmethod
    def get_strategy() -> ServiceManagementStrategy:
        """Return the appropriate service management strategy based on the environment."""
        if os.getenv("DOCKER_CONTAINER", "false").lower() == "true" or os.path.exists(
            "/.dockerenv"
        ):
            return DockerSupervisordStrategy()
        else:
            return EmbeddedSystemdStrategy()
