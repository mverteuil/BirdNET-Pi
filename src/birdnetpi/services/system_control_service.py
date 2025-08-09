from birdnetpi.utils.service_strategies import ServiceStrategySelector


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
