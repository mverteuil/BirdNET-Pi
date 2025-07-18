import abc
import subprocess
import os

class ServiceManagementStrategy(abc.ABC):
    """
    Abstract Base Class for service management strategies.
    Defines the interface for different service management implementations (e.g., systemd, supervisord).
    """

    @abc.abstractmethod
    def start_service(self, service_name: str) -> None:
        """Starts a specified system service."""
        pass

    @abc.abstractmethod
    def stop_service(self, service_name: str) -> None:
        """Stops a specified system service."""
        pass

    @abc.abstractmethod
    def restart_service(self, service_name: str) -> None:
        """Restarts a specified system service."""
        pass

    @abc.abstractmethod
    def enable_service(self, service_name: str) -> None:
        """Enables a specified system service to start on boot."""
        pass

    @abc.abstractmethod
    def disable_service(self, service_name: str) -> None:
        """Disables a specified system service from starting on boot."""
        pass

    @abc.abstractmethod
    def get_service_status(self, service_name: str) -> str:
        """Returns the status of a specified system service."""
        pass

class EmbeddedSystemdStrategy(ServiceManagementStrategy):
    """
    Service management strategy for systems using systemd (e.g., Raspberry Pi OS).
    """
    def _run_systemctl_command(self, action: str, service_name: str) -> None:
        try:
            subprocess.run(["sudo", "systemctl", action, service_name], check=True)
            print(f"Service {service_name} {action}ed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error {action}ing service {service_name}: {e}")
        except FileNotFoundError:
            print("Error: systemctl command not found. Is systemd installed?")

    def start_service(self, service_name: str) -> None:
        self._run_systemctl_command("start", service_name)

    def stop_service(self, service_name: str) -> None:
        self._run_systemctl_command("stop", service_name)

    def restart_service(self, service_name: str) -> None:
        self._run_systemctl_command("restart", service_name)

    def enable_service(self, service_name: str) -> None:
        self._run_systemctl_command("enable", service_name)

    def disable_service(self, service_name: str) -> None:
        self._run_systemctl_command("disable", service_name)

    def get_service_status(self, service_name: str) -> str:
        try:
            result = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Error getting status for {service_name}: {e.stderr.strip()}"
        except FileNotFoundError:
            return "Error: systemctl command not found."

class DockerSupervisordStrategy(ServiceManagementStrategy):
    """
    Service management strategy for Docker containers using Supervisord.
    """
    def _run_supervisorctl_command(self, action: str, service_name: str) -> None:
        try:
            # Assuming supervisorctl is available in the PATH within the Docker container
            subprocess.run(["supervisorctl", action, service_name], check=True)
            print(f"Service {service_name} {action}ed successfully via supervisorctl.")
        except subprocess.CalledProcessError as e:
            print(f"Error {action}ing service {service_name} via supervisorctl: {e}")
        except FileNotFoundError:
            print("Error: supervisorctl command not found. Is Supervisord installed and configured?")

    def start_service(self, service_name: str) -> None:
        self._run_supervisorctl_command("start", service_name)

    def stop_service(self, service_name: str) -> None:
        self._run_supervisorctl_command("stop", service_name)

    def restart_service(self, service_name: str) -> None:
        self._run_supervisorctl_command("restart", service_name)

    def enable_service(self, service_name: str) -> None:
        print(f"Enabling service {service_name} is not directly supported by supervisorctl in the same way as systemd. "
              "Services are typically enabled by their presence in supervisord.conf.")

    def disable_service(self, service_name: str) -> None:
        print(f"Disabling service {service_name} is not directly supported by supervisorctl in the same way as systemd. "
              "To disable, remove or comment out the service from supervisord.conf.")

    def get_service_status(self, service_name: str) -> str:
        try:
            result = subprocess.run(["supervisorctl", "status", service_name], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Error getting status for {service_name} via supervisorctl: {e.stderr.strip()}"
        except FileNotFoundError:
            return "Error: supervisorctl command not found."

class ServiceStrategySelector:
    """
    Selects the appropriate service management strategy based on the environment.
    """
    @staticmethod
    def get_strategy() -> ServiceManagementStrategy:
        if os.getenv("DOCKER_CONTAINER", "false").lower() == "true" or os.path.exists("/.dockerenv"):
            return DockerSupervisordStrategy()
        else:
            return EmbeddedSystemdStrategy()
