"""Structlog-based logging configuration for BirdNET-Pi.

This module provides structured logging configuration using structlog,
replacing the standard logging system with better structured output
and git version tracking.

Supports different deployment targets:
- SBC: Uses journald for system integration
- Docker: Uses stdout with structured output
- Development: Configurable JSON or human-readable output
"""

import logging
import logging.handlers
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.file_path_resolver import FilePathResolver


def is_docker_environment() -> bool:
    """Check if running in a Docker container."""
    return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"


def is_systemd_available() -> bool:
    """Check if systemd/journald is available on the system."""
    try:
        result = subprocess.run(
            ["systemctl", "--version"],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_git_version() -> str:
    """Get the current git branch and commit hash for version logging."""
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

        # Get current commit hash (short)
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"

        return f"{branch}@{commit}"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def add_git_version(
    logger: structlog.BoundLogger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add git version information to log entries."""
    event_dict["version"] = get_git_version()
    return event_dict


def _get_environment_config() -> tuple[bool, bool, bool]:
    """Detect deployment environment and return configuration flags."""
    is_docker = is_docker_environment()
    has_systemd = is_systemd_available()
    is_development = os.environ.get("BIRDNETPI_ENV", "production") == "development"
    return is_docker, has_systemd, is_development


def _configure_processors(is_docker: bool, has_systemd: bool, is_development: bool) -> list:
    """Configure structlog processors based on environment."""
    processors = [
        structlog.contextvars.merge_contextvars,
        add_git_version,
        structlog.processors.add_log_level,
        structlog.processors.add_logger_name,
        structlog.processors.TimeStamper(fmt="ISO"),
    ]

    if is_docker or (has_systemd and not is_development):
        processors.append(structlog.processors.JSONRenderer())
    else:
        dev_json_logs = os.environ.get("BIRDNETPI_JSON_LOGS", "false").lower() == "true"
        if dev_json_logs:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer(colors=True))

    return processors


def _configure_handlers(
    config: BirdNETConfig, is_docker: bool, has_systemd: bool, is_development: bool
) -> None:
    """Configure logging handlers based on environment."""
    file_resolver = FilePathResolver()
    root_logger = logging.getLogger()
    log_level = getattr(logging, config.logging.log_level.upper(), logging.INFO)

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(log_level)

    # Environment-specific handler configuration
    if is_docker or not has_systemd or is_development:
        # Console output for Docker and development
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(console_handler)

    # File logging for development if enabled
    if is_development and config.logging.file_logging_enabled:
        _add_file_handler(config, file_resolver, root_logger, log_level)

    # Journald for SBC deployments
    if has_systemd and not is_development:
        _add_journald_handler(config, root_logger, log_level)

    # Additional syslog if explicitly enabled
    if config.logging.syslog_enabled:
        _add_syslog_handler(config, root_logger, log_level)


def _add_file_handler(
    config: BirdNETConfig,
    file_resolver: FilePathResolver,
    root_logger: logging.Logger,
    log_level: int,
) -> None:
    """Add file logging handler."""
    log_file_path = config.logging.log_file_path
    if not log_file_path:
        log_file_path = str(Path(file_resolver.get_temp_dir()) / "birdnetpi.log")
    else:
        log_file_path = os.path.expanduser(log_file_path)

    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=config.logging.max_log_file_size_mb * 1024 * 1024,
        backupCount=config.logging.log_file_backup_count,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(file_handler)


def _add_journald_handler(
    config: BirdNETConfig, root_logger: logging.Logger, log_level: int
) -> None:
    """Add journald handler for SBC deployments."""
    try:
        from systemd import journal

        journal_handler = journal.JournalHandler()
        journal_handler.setLevel(log_level)
        journal_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(journal_handler)
    except ImportError:
        # Fallback to syslog if systemd-python not available
        if config.logging.syslog_enabled:
            _add_syslog_handler(config, root_logger, log_level)


def _add_syslog_handler(config: BirdNETConfig, root_logger: logging.Logger, log_level: int) -> None:
    """Add syslog handler."""
    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address=(config.logging.syslog_host, config.logging.syslog_port)
        )
        syslog_handler.setLevel(log_level)
        syslog_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(syslog_handler)
    except Exception as e:
        logger = structlog.get_logger(__name__)
        logger.error("Failed to configure syslog", error=str(e))


def configure_structlog(config: BirdNETConfig) -> None:
    """Configure structlog-based logging system.

    Automatically detects deployment environment and configures accordingly:
    - Docker: Uses stdout with JSON output
    - SBC with systemd: Uses journald
    - Development: Uses file/console based on config (supports both JSON and human-readable)

    Args:
        config: The BirdNETConfig instance containing logging settings.
    """
    # Detect environment
    is_docker, has_systemd, is_development = _get_environment_config()

    # Configure processors
    processors = _configure_processors(is_docker, has_systemd, is_development)

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.logging.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure handlers
    _configure_handlers(config, is_docker, has_systemd, is_development)

    # Log configuration success
    logger = structlog.get_logger(__name__)
    logger.info(
        "Structured logging configured",
        git_version=get_git_version(),
        log_level=config.logging.log_level,
        environment="docker" if is_docker else ("sbc" if has_systemd else "development"),
        file_logging=is_development and config.logging.file_logging_enabled,
        journald=has_systemd and not is_development,
        syslog=config.logging.syslog_enabled,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog BoundLogger instance
    """
    return structlog.get_logger(name)
