"""BirdNET-Pi web application with clean architecture and dependency injection."""

import logging

from birdnetpi.config import ConfigManager
from birdnetpi.system.structlog_configurator import configure_structlog
from birdnetpi.web.core.factory import create_app

# Configure logging before anything else imports and creates loggers
config_manager = ConfigManager()
config = config_manager.load()
configure_structlog(config)

# Disable uvicorn access logger since we have our own structured logging middleware
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.disabled = True

# Keep uvicorn error logger for startup/shutdown messages
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.setLevel(logging.INFO)

app = create_app()
