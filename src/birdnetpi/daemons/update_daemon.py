"""Update daemon for managing system updates.

This daemon runs in three modes:
- migrate: One-shot mode for migrations and recovery (both Docker and SBC)
- monitor: Long-running monitoring only (Docker post-migration)
- both: Long-running with full update capability (SBC only)
"""

import asyncio
import json
import logging
import signal
import sys
from types import FrameType

import aiohttp.web
import click

from birdnetpi.config import ConfigManager
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.releases.region_pack_service import RegionPackService
from birdnetpi.releases.update_manager import StateFileManager, UpdateManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.structlog_configurator import configure_structlog
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.utils.cache import Cache

logger = logging.getLogger(__name__)


class DaemonState:
    """Encapsulates daemon state to avoid module-level globals."""

    shutdown_flag: bool = False
    mode: str = "monitor"
    update_manager: UpdateManager | None = None
    cache_service: Cache | None = None
    config_manager: ConfigManager | None = None
    region_pack_service: RegionPackService | None = None
    update_in_progress: bool = False
    critical_section: bool = False
    pending_signals: list[int] = []  # noqa: RUF012 - Mutable default is intentional
    http_server: aiohttp.web.AppRunner | None = None

    @classmethod
    def reset(cls) -> None:
        """Reset state to initial values (useful for testing)."""
        cls.shutdown_flag = False
        cls.mode = "monitor"
        cls.update_manager = None
        cls.cache_service = None
        cls.config_manager = None
        cls.region_pack_service = None
        cls.update_in_progress = False
        cls.critical_section = False
        cls.pending_signals = []
        cls.http_server = None


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle signals with protection for critical sections."""
    # During critical operations (like database migrations), queue the signal
    if DaemonState.critical_section:
        logger.warning("Signal %s received during critical section, queueing for later", signum)
        DaemonState.pending_signals.append(signum)
        return

    # During non-critical update operations, allow graceful completion
    if DaemonState.update_in_progress:
        logger.info("Signal %s received during update, will shutdown after current stage", signum)
        DaemonState.shutdown_flag = True
        return

    # Normal shutdown
    logger.info("Signal %s received, initiating shutdown...", signum)
    DaemonState.shutdown_flag = True


async def handle_sse_stream(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    """Server-Sent Events stream for real-time update progress."""
    response = aiohttp.web.StreamResponse()
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"  # Disable Nginx buffering

    await response.prepare(request)

    try:
        while not DaemonState.shutdown_flag:
            if not DaemonState.update_manager:
                await asyncio.sleep(1)
                continue

            # Read current state
            state = StateFileManager(
                DaemonState.update_manager.file_manager, DaemonState.update_manager.path_resolver
            )
            current_state = state.read_state()

            if current_state:
                # Send as SSE event
                event_data = f"data: {json.dumps(current_state)}\n\n"
                await response.write(event_data.encode("utf-8"))
            else:
                # Send heartbeat to keep connection alive
                await response.write(b": heartbeat\n\n")

            await response.drain()  # Ensure data is sent
            await asyncio.sleep(1)

    except (ConnectionResetError, ConnectionAbortedError):
        # Client disconnected - normal for SSE
        pass

    return response


async def start_http_server() -> None:
    """Start HTTP server for SSE streaming endpoint."""
    # Create aiohttp application
    app = aiohttp.web.Application()

    # Add ONLY the SSE stream endpoint
    app.router.add_get("/api/update/stream", handle_sse_stream)
    # NO control endpoints - all control via Redis

    # Configure runner
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()

    # Start TCP site on localhost only (security)
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 8889)
    await site.start()

    DaemonState.http_server = runner
    logger.info("Update HTTP server started on 127.0.0.1:8889")


async def run_monitor_loop() -> None:  # noqa: C901 - Reasonable complexity for monitoring loop
    """Monitor mode for Docker - check for updates only, no apply capability."""
    # Load config to get update settings
    config = DaemonState.config_manager.load() if DaemonState.config_manager else None

    # Check on startup if configured
    if config and config.updates.auto_check_on_startup:
        logger.info("Performing startup update check")
        if DaemonState.update_manager:
            try:
                status = await DaemonState.update_manager.check_for_updates()
                if DaemonState.cache_service:
                    # Cache for the configured interval
                    ttl = config.updates.check_interval_hours * 3600
                    DaemonState.cache_service.set("update:status", status, ttl=ttl)
                available = status.get("available", False)
                logger.info("Startup update check completed: available=%s", available)
            except Exception as e:
                logger.error("Startup update check failed: %s", e)

    last_check_time = asyncio.get_event_loop().time()

    while not DaemonState.shutdown_flag:
        try:
            # Reload config to pick up any changes
            config = DaemonState.config_manager.load() if DaemonState.config_manager else None
            if not config:
                await asyncio.sleep(60)  # Retry in a minute if config unavailable
                continue

            # Check Redis for status requests (from FastAPI)
            if DaemonState.cache_service:
                status_request = DaemonState.cache_service.get("update:request")
                if status_request and status_request.get("action") == "check":
                    # Process check request
                    if DaemonState.update_manager:
                        status = await DaemonState.update_manager.check_for_updates()
                    else:
                        status = {"available": False}
                    if DaemonState.cache_service:
                        ttl = config.updates.check_interval_hours * 3600
                        DaemonState.cache_service.set("update:status", status, ttl=ttl)
                        DaemonState.cache_service.delete("update:request")
                    logger.info("Update check completed via Redis request")
                    last_check_time = asyncio.get_event_loop().time()
                else:
                    # Periodic update check based on configuration
                    current_time = asyncio.get_event_loop().time()
                    time_since_last_check = current_time - last_check_time
                    check_interval_seconds = config.updates.check_interval_hours * 3600

                    if (
                        config.updates.check_enabled
                        and time_since_last_check >= check_interval_seconds
                    ):
                        check_hours = config.updates.check_interval_hours
                        logger.info(
                            "Performing periodic update check (interval: %d hours)", check_hours
                        )
                        if DaemonState.update_manager:
                            status = await DaemonState.update_manager.check_for_updates()
                        else:
                            status = {"available": False}

                        # Store in Redis for FastAPI to read
                        if DaemonState.cache_service:
                            DaemonState.cache_service.set(
                                "update:status",
                                status,
                                ttl=check_interval_seconds,
                            )
                        last_check_time = current_time

            # Check for region pack download requests
            region_pack_request = check_for_region_pack_request()
            if region_pack_request:
                await process_region_pack_download(region_pack_request)

            # Short sleep to check for requests frequently
            await asyncio.sleep(10)  # Check every 10 seconds

        except Exception as e:
            logger.error("Update check failed: %s", e)
            await asyncio.sleep(300)


def check_for_update_request() -> dict | None:
    """Check Redis for update requests.

    Returns:
        Update request dict or None if no request.
    """
    if not DaemonState.cache_service:
        return None

    try:
        return DaemonState.cache_service.get("update:request")
    except Exception as e:
        logger.error("Failed to check Redis for update request: %s", e)
        return None


def check_for_region_pack_request() -> dict | None:
    """Check Redis for region pack download requests.

    Returns:
        Region pack download request dict or None if no request.
    """
    if not DaemonState.cache_service:
        return None

    try:
        return DaemonState.cache_service.get("region_pack:download_request")
    except Exception as e:
        logger.error("Failed to check Redis for region pack request: %s", e)
        return None


async def process_region_pack_download(request: dict) -> None:
    """Process a region pack download request.

    Args:
        request: The download request containing region_id, download_url, size_mb.
    """
    if not DaemonState.region_pack_service or not DaemonState.cache_service:
        logger.error("Region pack service or cache not initialized")
        return

    region_id = request.get("region_id")
    download_url = request.get("download_url")
    size_mb = request.get("size_mb", 0)

    if not region_id or not download_url:
        logger.error("Invalid region pack request: missing region_id or download_url")
        DaemonState.cache_service.delete("region_pack:download_request")
        return

    logger.info("Processing region pack download: %s (%.1f MB)", region_id, size_mb)

    # Store download status for UI
    DaemonState.cache_service.set(
        "region_pack:download_status",
        {"status": "downloading", "region_id": region_id, "progress": 0},
        ttl=3600,
    )

    try:
        region_pack_service = DaemonState.region_pack_service

        def progress_callback(downloaded_mb: float, total_mb: float) -> None:
            """Update download progress in cache."""
            if DaemonState.cache_service and total_mb > 0:
                progress = int((downloaded_mb / total_mb) * 100)
                DaemonState.cache_service.set(
                    "region_pack:download_status",
                    {
                        "status": "downloading",
                        "region_id": region_id,
                        "progress": progress,
                        "downloaded_mb": round(downloaded_mb, 1),
                        "total_mb": round(total_mb, 1),
                    },
                    ttl=3600,
                )

        # Run download in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: region_pack_service.download_from_url(
                region_id=region_id,
                download_url=download_url,
                size_mb=size_mb,
                force=True,
                progress_callback=progress_callback,
            ),
        )

        # Update status to complete
        DaemonState.cache_service.set(
            "region_pack:download_status",
            {"status": "complete", "region_id": region_id, "progress": 100},
            ttl=300,
        )
        logger.info("Region pack '%s' downloaded and installed successfully", region_id)

    except Exception as e:
        logger.error("Failed to download region pack '%s': %s", region_id, e)
        DaemonState.cache_service.set(
            "region_pack:download_status",
            {"status": "error", "region_id": region_id, "error": str(e)},
            ttl=300,
        )

    finally:
        # Clear the download request
        DaemonState.cache_service.delete("region_pack:download_request")


async def process_update_request(update_request: dict) -> None:  # noqa: C901 - Reasonable complexity for update handling
    """Process a single update request.

    Args:
        update_request: The update request to process.
    """
    action = update_request.get("action")

    if action == "check":
        # Process check request
        if DaemonState.update_manager:
            status = await DaemonState.update_manager.check_for_updates()
        else:
            status = {"available": False, "error": "Update manager not initialized"}

        if DaemonState.cache_service:
            DaemonState.cache_service.set("update:status", status)
            DaemonState.cache_service.delete("update:request")
        logger.info("Update check completed via Redis request")

    elif action == "apply":
        version = update_request["version"]
        dry_run = update_request.get("dry_run", False)
        logger.info("Processing update request: %s (dry_run=%s)", version, dry_run)

        # Mark update as in progress
        DaemonState.update_in_progress = True

        try:
            # Delegate actual update to UpdateManager
            if dry_run:
                # TODO: Implement test_update method
                logger.info("Dry run not yet implemented")
                result = {"success": False, "error": "Dry run not implemented"}
            else:
                if DaemonState.update_manager:
                    result = await DaemonState.update_manager.apply_update(version)
                else:
                    result = {"success": False, "error": "Update manager not initialized"}

            # Store result for web UI
            if DaemonState.cache_service:
                DaemonState.cache_service.set("update:result", result)

        finally:
            # Clear update status
            DaemonState.update_in_progress = False
            if DaemonState.cache_service:
                DaemonState.cache_service.delete("update:request")

            # Process any pending signals after update completes
            if DaemonState.pending_signals:
                logger.info("Processing %d queued signals", len(DaemonState.pending_signals))
                for sig in DaemonState.pending_signals:
                    _signal_handler(sig, None)
                DaemonState.pending_signals.clear()


async def _perform_startup_check(config: BirdNETConfig | None) -> None:
    """Perform update check on startup if configured.

    Args:
        config: The configuration object.
    """
    if not (config and config.updates.auto_check_on_startup):
        return

    logger.info("Performing startup update check")
    if not (DaemonState.cache_service and DaemonState.update_manager):
        return

    try:
        status = await DaemonState.update_manager.check_for_updates()
        ttl = config.updates.check_interval_hours * 3600
        DaemonState.cache_service.set("update:status", status, ttl=ttl)
        available = status.get("available", False)
        logger.info("Startup update check completed: available=%s", available)
    except Exception as e:
        logger.error("Startup update check failed: %s", e)


async def _handle_periodic_check(
    config: BirdNETConfig, current_time: float, last_check_time: float
) -> float:
    """Handle periodic update checks based on configuration.

    Args:
        config: The configuration object.
        current_time: Current event loop time.
        last_check_time: Time of last check.

    Returns:
        Updated last check time.
    """
    time_since_last_check = current_time - last_check_time
    check_interval_seconds = config.updates.check_interval_hours * 3600

    if not (config.updates.check_enabled and time_since_last_check >= check_interval_seconds):
        return last_check_time

    logger.info(
        "Performing periodic update check (interval: %d hours)",
        config.updates.check_interval_hours,
    )

    if DaemonState.cache_service and DaemonState.update_manager:
        status = await DaemonState.update_manager.check_for_updates()
        DaemonState.cache_service.set("update:status", status, ttl=check_interval_seconds)

    return current_time


async def run_update_with_redis_monitoring() -> None:
    """Monitor Redis for update requests and apply them (SBC mode)."""
    # Load config to get update settings
    config = DaemonState.config_manager.load() if DaemonState.config_manager else None

    # Check on startup if configured
    await _perform_startup_check(config)

    last_check_time = asyncio.get_event_loop().time()

    while not DaemonState.shutdown_flag:
        try:
            # Reload config to pick up any changes
            config = DaemonState.config_manager.load() if DaemonState.config_manager else None
            if not config:
                await asyncio.sleep(60)  # Retry in a minute if config unavailable
                continue

            # Periodic update check based on configuration
            current_time = asyncio.get_event_loop().time()
            last_check_time = await _handle_periodic_check(config, current_time, last_check_time)

            # Check for queued update requests
            update_request = check_for_update_request()
            if update_request:
                await process_update_request(update_request)
                # Reset check time after processing a manual request
                if update_request.get("action") == "check":
                    last_check_time = asyncio.get_event_loop().time()

            # Check for region pack download requests
            region_pack_request = check_for_region_pack_request()
            if region_pack_request:
                await process_region_pack_download(region_pack_request)

            # Sleep before next check
            await asyncio.sleep(10)  # Check every 10 seconds

        except Exception as e:
            logger.error("Update daemon error: %s", e)
            await asyncio.sleep(60)


def _initialize_services() -> tuple[PathResolver, FileManager, ConfigManager]:
    """Initialize core services for the daemon.

    Returns:
        Tuple of (path_resolver, file_manager, config_manager).
    """
    path_resolver = PathResolver()
    file_manager = FileManager(path_resolver)
    system_control = SystemControlService()
    config_manager = ConfigManager(path_resolver)

    # Configure logging
    config = config_manager.load()
    configure_structlog(config)

    # Create UpdateManager with all dependencies
    DaemonState.update_manager = UpdateManager(
        path_resolver=path_resolver, file_manager=file_manager, system_control=system_control
    )

    # Create RegionPackService for region pack downloads
    DaemonState.region_pack_service = RegionPackService(path_resolver)

    DaemonState.config_manager = config_manager

    return path_resolver, file_manager, config_manager


def _initialize_cache(mode: str) -> int:
    """Initialize cache service.

    Args:
        mode: The daemon mode.

    Returns:
        0 on success, 1 if cache required but unavailable.
    """
    try:
        DaemonState.cache_service = Cache(
            redis_host="127.0.0.1",
            redis_port=6379,
            redis_db=0,
            default_ttl=300,
            enable_cache_warming=False,
        )
        return 0
    except RuntimeError as e:
        logger.error("Failed to connect to Redis: %s", e)
        # In monitor mode, we can't function without Redis
        if mode == "monitor":
            return 1
        # In other modes, we can continue without Redis
        DaemonState.cache_service = None
        return 0


def _check_update_state(file_manager: FileManager, path_resolver: PathResolver) -> None:
    """Check for interrupted update on startup.

    Args:
        file_manager: The file manager instance.
        path_resolver: The path resolver instance.
    """
    state_manager = StateFileManager(file_manager, path_resolver)
    current_state = state_manager.read_state()

    if current_state and current_state.get("phase") == "daemon_restart_needed":
        # Update completed successfully
        logger.info("Update to %s completed successfully", current_state.get("target_version"))
        state_manager.clear_state()
    elif current_state and current_state.get("phase"):
        # Update was interrupted
        logger.error("Update interrupted at phase: %s", current_state["phase"])
        # TODO: Implement recovery or rollback
        # await DaemonState.update_manager.attempt_recovery()


async def _run_migrate_mode() -> int:
    """Run the daemon in migrate mode.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger.info("Running database migrations...")

    # Enter critical section to prevent interruption during migrations
    DaemonState.critical_section = True
    try:
        # Run Alembic migrations
        if DaemonState.update_manager:
            await DaemonState.update_manager._run_migrations()
            logger.info("Database migrations completed successfully")
        else:
            logger.error("UpdateManager not initialized")
            return 1
        return 0
    except Exception as e:
        logger.error("Migration failed: %s", e)
        return 1
    finally:
        # Exit critical section
        DaemonState.critical_section = False

        # Process any queued signals
        if DaemonState.pending_signals:
            logger.info("Processing %d queued signals", len(DaemonState.pending_signals))
            for sig in DaemonState.pending_signals:
                _signal_handler(sig, None)
            DaemonState.pending_signals.clear()


async def run(mode: str) -> int:
    """Run the update daemon in the specified mode."""
    # Initialize services
    path_resolver, file_manager, _ = _initialize_services()
    DaemonState.mode = mode

    # Initialize cache
    cache_result = _initialize_cache(mode)
    if cache_result != 0:
        return cache_result

    # Check for interrupted update on startup
    _check_update_state(file_manager, path_resolver)

    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)  # Prevent reload during updates

    logger.info("Update daemon starting in %s mode", mode)

    # Start HTTP server for update endpoints
    if mode in ["monitor", "both"]:
        await start_http_server()

    # Run based on mode
    if mode == "migrate":
        return await _run_migrate_mode()
    elif mode == "monitor":
        # Docker: Monitor only, provide status via HTTP
        await run_monitor_loop()
    elif mode == "both":
        # SBC: Full update capability via Redis queue monitoring
        await run_update_with_redis_monitoring()

    # Clean shutdown
    if DaemonState.http_server:
        await DaemonState.http_server.cleanup()

    return 0


@click.command()
@click.option(
    "--mode",
    type=click.Choice(["migrate", "monitor", "both"]),
    default="monitor",
    help="Daemon mode: migrate (one-shot), monitor (check only), both (full capability)",
)
def main(mode: str) -> None:
    """Start the update daemon."""
    # Run the async main with asyncio
    try:
        exit_code = asyncio.run(run(mode))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Update daemon stopped by user")
    except Exception as e:
        logger.error("Update daemon failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
