import abc
import os
import subprocess


class ServiceManagementStrategy(abc.ABC):
    """Abstract Base Class for service management strategies.

    Defines the interface for different service management implementations (e.g., systemd, supervisord).
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


class EmbeddedSystemdStrategy(ServiceManagementStrategy):
    """Service management strategy for systems using systemd (e.g., Raspberry Pi OS)."""

    def _run_systemctl_command(self, action: str, service_name: str) -> None:
        try:
            subprocess.run(["sudo", "systemctl", action, service_name], check=True)
            print(f"Service {service_name} {action}ed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error {action}ing service {service_name}: {e}")
        except FileNotFoundError:
            print("Error: systemctl command not found. Is systemd installed?")

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
            print("Error: systemctl command not found. Is systemd installed?")
            return "error"


class DockerSupervisordStrategy(ServiceManagementStrategy):
    """Service management strategy for Docker containers using Supervisord."""

    def _run_supervisorctl_command(self, action: str, service_name: str) -> None:
        try:
            # Assuming supervisorctl is available in the PATH within the Docker container
            subprocess.run(["supervisorctl", action, service_name], check=True)
            print(f"Service {service_name} {action}ed successfully via supervisorctl.")
        except subprocess.CalledProcessError as e:
            print(f"Error {action}ing service {service_name} via supervisorctl: {e}")
        except FileNotFoundError:
            print(
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
        print(
            f"Enabling service {service_name} is not directly supported by supervisorctl in the same way as systemd. "
            "Supervisor manages processes based on its configuration."
        )

    def disable_service(self, service_name: str) -> None:
        """Disable a specified system service from starting on boot."""
        print(
            f"Disabling service {service_name} is not directly supported by supervisorctl in the same way as systemd. "
            "To disable, remove it from Supervisor's configuration."
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
            if f"{service_name} RUNNING" in output:
                return "active"
            elif f"{service_name} STOPPED" in output:
                return "inactive"
            else:
                return "unknown"
        except FileNotFoundError:
            print("Error: supervisorctl command not found. Is Supervisor installed?")
            return "error"


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
