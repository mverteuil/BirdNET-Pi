import abc
import logging
import os
import subprocess

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
                ["systemctl", "is-active", service_name],
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
