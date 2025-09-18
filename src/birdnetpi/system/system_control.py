from typing import Any

from birdnetpi.system.service_strategies import ServiceStrategySelector


class SystemControlService:
    """Service for controlling system services with methods to start, stop, and restart them."""

    def __init__(self):
        self.strategy = ServiceStrategySelector.get_strategy()

    def restart_service(self, service_name: str) -> None:
        """Restarts a specified system service."""
        self.strategy.restart_service(service_name)

    def stop_service(self, service_name: str) -> None:
        """Stop a specified system service."""
        self.strategy.stop_service(service_name)

    def start_service(self, service_name: str) -> None:
        """Start a specified system service."""
        self.strategy.start_service(service_name)

    def enable_service(self, service_name: str) -> None:
        """Enable a specified system service."""
        self.strategy.enable_service(service_name)

    def disable_service(self, service_name: str) -> None:
        """Disable a specified system service."""
        self.strategy.disable_service(service_name)

    def get_service_status(self, service_name: str) -> str:
        """Get the status of a specified system service."""
        return self.strategy.get_service_status(service_name)

    def restart_services(self, services: list[str]) -> None:
        """Restarts a list of specified system services."""
        for service in services:
            self.restart_service(service)

    def daemon_reload(self) -> None:
        """Reload systemd daemon configuration (only applicable for systemd)."""
        self.strategy.daemon_reload()

    def get_service_details(self, service_name: str) -> dict[str, Any]:
        """Get detailed status including uptime for a service.

        Returns:
            Dictionary with status, pid, uptime_seconds, etc.
        """
        return self.strategy.get_service_details(service_name)

    def get_all_services_status(self, service_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Get status for all services in the list.

        Args:
            service_list: List of service configurations with name, description, etc.

        Returns:
            List of services with their current status and details.
        """
        services_with_status = []
        for service_config in service_list:
            service_name = service_config["name"]
            details = self.get_service_details(service_name)
            # Merge config with runtime details
            service_info = {**service_config, **details}
            services_with_status.append(service_info)
        return services_with_status

    def get_system_info(self) -> dict[str, Any]:
        """Get system/container information including uptime.

        Returns:
            Dictionary with uptime_seconds and reboot_available.
        """
        uptime_seconds = self.strategy.get_system_uptime()
        # Check if reboot is supported
        reboot_available = self.can_reboot()
        return {
            "uptime_seconds": uptime_seconds,
            "reboot_available": reboot_available,
        }

    def can_reboot(self) -> bool:
        """Check if system/container reboot is available."""
        # We'll determine this based on the strategy type and permissions
        # For now, assume it's available for SBC and check for Docker
        return True  # Will be refined based on actual permissions

    def reboot_system(self) -> bool:
        """Reboot the system/container if supported.

        Returns:
            True if reboot initiated, False otherwise.
        """
        return self.strategy.reboot_system()
