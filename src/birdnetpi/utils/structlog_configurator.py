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
from collections.abc import Callable
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
    """Get the current git branch and commit hash for version logging.

    Returns version in format: branch@SHA[:8]
    """
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

        # Get current commit hash (8 chars as requested)
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"

        return f"{branch}@{commit}"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def get_deployment_environment() -> str:
    """Get deployment environment with 'unknown' fallback."""
    if is_docker_environment():
        return "docker"
    elif is_systemd_available():
        return "sbc"
    elif os.environ.get("BIRDNETPI_ENV") == "development":
        return "development"
    else:
        return "unknown"


def _add_static_context(extra_fields: dict[str, str]) -> Callable:
    """Processor to add static context fields to all log entries."""

    def processor(
        logger: structlog.BoundLogger, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        event_dict.update(extra_fields)
        return event_dict

    return processor


def _get_environment_config() -> tuple[bool, bool, bool]:
    """Detect deployment environment and return configuration flags."""
    is_docker = is_docker_environment()
    has_systemd = is_systemd_available()
    is_development = os.environ.get("BIRDNETPI_ENV", "production") == "development"
    return is_docker, has_systemd, is_development


def _configure_processors(
    config: BirdNETConfig, is_docker: bool, has_systemd: bool, is_development: bool
) -> list:
    """Configure structlog processors based on environment."""
    # Build dynamic extra fields
    extra_fields = {
        "service": "birdnet-pi",
        "version": get_git_version(),
        "deployment": get_deployment_environment(),
        **config.logging.extra_fields,  # Allow config to override/add fields
    }

    # Add site_name if available
    if hasattr(config, "site_name") and config.site_name:
        extra_fields["site_name"] = config.site_name

    # Add location if available (for field deployments)
    if hasattr(config, "latitude") and hasattr(config, "longitude"):
        if config.latitude != 0.0 or config.longitude != 0.0:
            extra_fields["location"] = f"{config.latitude},{config.longitude}"

    processors = [
        structlog.contextvars.merge_contextvars,
        _add_static_context(extra_fields),
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
    ]

    # Add caller info if requested
    if config.logging.include_caller:
        processors.append(structlog.processors.CallsiteParameterAdder())

    # Determine JSON vs human-readable output
    use_json = config.logging.json_logs
    if use_json is None:
        # Auto-detect: JSON for Docker/SBC, human-readable for development
        use_json = is_docker or (has_systemd and not is_development)

    # Override with environment variable for development
    if is_development:
        dev_json_logs = os.environ.get("BIRDNETPI_JSON_LOGS", "false").lower() == "true"
        if dev_json_logs:
            use_json = True

    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    return processors


def _configure_handlers(
    config: BirdNETConfig, is_docker: bool, has_systemd: bool, is_development: bool
) -> None:
    """Configure logging handlers based on environment."""
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

    # Journald for SBC deployments (or systemd environments)
    if has_systemd:
        _add_journald_handler(config, root_logger, log_level)


def _add_journald_handler(
    config: BirdNETConfig, root_logger: logging.Logger, log_level: int
) -> None:
    """Add journald handler for systemd environments."""
    try:
        from systemd import journal  # type: ignore[import-untyped]

        journal_handler = journal.JournalHandler()
        journal_handler.setLevel(log_level)
        journal_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(journal_handler)
    except ImportError:
        # Fallback to stderr if systemd-python not available
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(log_level)
        stderr_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(stderr_handler)


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
    processors = _configure_processors(config, is_docker, has_systemd, is_development)

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.logging.level.upper(), logging.INFO)
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
        log_level=config.logging.level,
        environment=get_deployment_environment(),
        journald=has_systemd,
        json_output=config.logging.json_logs,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog BoundLogger instance
    """
    return structlog.get_logger(name)
