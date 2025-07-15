from enum import Enum


class LogLevel(Enum):
    """Represents different levels of logging severity."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
