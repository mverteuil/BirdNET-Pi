"""Application lifespan management for startup and shutdown events."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from birdnetpi.system.structlog_configurator import configure_structlog
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager for application startup and shutdown events.

    Handles the complete application lifecycle including:
    - Service initialization and dependency injection
    - Static file mounting and template configuration
    - Service startup and shutdown
    - Proper cleanup of resources

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control back to the application for normal operation.
    """
    # Get the container from the app (ignore type error - runtime dynamic attribute)
    container: Container = app.container  # type: ignore[attr-defined]

    # Configure structured logging based on loaded config
    config = container.config()
    configure_structlog(config)

    # Initialize file resolver and mount static files
    path_resolver = container.path_resolver()
    app.mount(
        "/static",
        StaticFiles(directory=path_resolver.get_static_dir()),
        name="static",
    )

    # Initialize Jinja2Templates
    templates = Jinja2Templates(directory=path_resolver.get_templates_dir())

    # Store essential components that routers might need
    # Note: We avoid using app.state and instead rely on dependency injection
    # But we keep templates accessible as it's needed for rendering
    app.extra = {"templates": templates}

    # Get notification service and its websockets set
    notification_manager = container.notification_manager()
    # The websockets set is already initialized in the container
    # No need to create a new one or reassign private attributes
    app.extra["active_websockets"] = notification_manager.active_websockets  # type: ignore[assignment]

    # Configure webhook service from config
    webhook_service = container.webhook_service()
    webhook_urls = config.webhook_urls
    if webhook_urls:
        # Handle both list and string formats for backward compatibility
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        webhook_service.configure_webhooks_from_urls(webhook_url_list)

    # Register notification listeners
    notification_manager.register_listeners()

    logger.info("Starting application services...")

    # Start all services in proper order
    try:
        # Skip audio services - handled by standalone audio_websocket_daemon for better reliability

        # Start field mode services
        await container.gps_service().start()
        # hardware_monitor_manager has been removed - functionality moved to SystemInspector

        # Start IoT services
        await container.mqtt_service().start()
        await container.webhook_service().start()

        logger.info("All services started successfully")

        yield

    finally:
        logger.info("Shutting down application services...")

        # Cleanup: Stop services in reverse order
        try:
            await container.webhook_service().stop()
            await container.mqtt_service().stop()
            # hardware_monitor_manager has been removed - functionality moved to SystemInspector
            await container.gps_service().stop()
            # Skip audio services - handled by standalone audio_websocket_daemon

            logger.info("All services stopped successfully")

        except Exception as e:
            logger.error(f"Error during service shutdown: {e}")
            raise
