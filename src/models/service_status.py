from enum import Enum


class ServiceStatus(Enum):
    """Represents the operational status of a system service."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"
