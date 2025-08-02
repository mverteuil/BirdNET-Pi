import logging
import logging.handlers
import os

from birdnetpi.models.config import BirdNETConfig


def configure_logging(config: BirdNETConfig) -> None:
    """Configure the application's logging system based on the provided BirdNETConfig.

    Args:
        config: The BirdNETConfig instance containing logging settings.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Default level, can be overridden by config

    # Clear existing handlers to prevent duplicate logs in re-runs (e.g., in tests)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console Handler (always add for basic visibility)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Syslog Handler (if enabled in config)
    if config.logging.syslog_enabled:
        try:
            syslog_handler = logging.handlers.SysLogHandler(
                address=(config.logging.syslog_host, config.logging.syslog_port)
            )
            syslog_handler.setFormatter(formatter)
            root_logger.addHandler(syslog_handler)
        except Exception as e:
            root_logger.error(f"Failed to set up SyslogHandler: {e}")

    # File Handler (if enabled in config)
    if config.logging.file_logging_enabled:
        try:
            log_file_path = os.path.expanduser(config.logging.log_file_path)
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=config.logging.max_log_file_size_mb * 1024 * 1024,
                backupCount=config.logging.log_file_backup_count,
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.error(f"Failed to set up FileHandler: {e}")

    # Set log level from config if available
    if config.logging.log_level:
        try:
            root_logger.setLevel(config.logging.log_level.upper())
        except ValueError:
            root_logger.warning(
                f"Invalid log level '{config.logging.log_level}'. Defaulting to INFO."
            )
            root_logger.setLevel(logging.INFO)

    root_logger.info("Logging configured successfully.")
