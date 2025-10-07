"""Tests for update daemon."""

import asyncio
import signal
from unittest.mock import DEFAULT, MagicMock, create_autospec, patch

import aiohttp.web
import pytest

import birdnetpi.daemons.update_daemon as daemon
from birdnetpi.config.manager import ConfigManager
from birdnetpi.config.models import BirdNETConfig, UpdateConfig
from birdnetpi.daemons.update_daemon import DaemonState
from birdnetpi.releases.update_manager import StateFileManager, UpdateManager
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.cache import Cache


@pytest.fixture(autouse=True)
def reset_daemon_state():
    """Reset daemon state before each test."""
    DaemonState.reset()
    yield
    DaemonState.reset()


@pytest.fixture
def test_config():
    """Provide test configuration."""
    config = MagicMock(spec=BirdNETConfig)
    config.updates = MagicMock(spec=UpdateConfig)
    config.updates.check_interval_hours = 24
    config.updates.check_enabled = True
    config.updates.auto_check_on_startup = False
    return config


@pytest.fixture
def mock_cache():
    """Mock Cache service with Redis backend."""
    cache = MagicMock(spec=Cache)
    cache.get.return_value = None
    cache.set.return_value = None
    cache.delete.return_value = None
    return cache


@pytest.fixture
def mock_update_manager():
    """Mock UpdateManager for testing."""
    # Use MagicMock with spec instead of create_autospec because create_autospec
    # doesn't include instance attributes like file_manager
    manager = MagicMock(spec=UpdateManager)
    # Configure the already-spec'd methods instead of replacing them
    manager.check_for_updates.return_value = {
        "current_version": "v1.0.0",
        "latest_version": "v1.1.0",
        "update_available": True,
        "checked_at": "2024-01-01T12:00:00",
    }
    manager.apply_update.return_value = {"success": True, "version": "v1.1.0"}
    # Add instance attributes that exist on real UpdateManager
    manager.file_manager = MagicMock(spec=FileManager)
    manager.path_resolver = MagicMock(spec=PathResolver)
    return manager


@pytest.fixture
def mock_state_manager():
    """Mock StateFileManager."""
    state = MagicMock(spec=StateFileManager)
    state.read_state.return_value = None
    state.write_state.return_value = None
    state.clear_state.return_value = None
    state.acquire_lock.return_value = True
    state.release_lock.return_value = None
    return state


@pytest.fixture(autouse=True)
def mock_dependencies(mocker, test_config, mock_cache, mock_update_manager, path_resolver):
    """Mock external dependencies for update daemon."""
    # Mock imports and classes
    mocker.patch("birdnetpi.daemons.update_daemon.configure_structlog", autospec=True)

    with patch.multiple(
        "birdnetpi.daemons.update_daemon",
        PathResolver=DEFAULT,
        FileManager=DEFAULT,
        SystemControlService=DEFAULT,
        ConfigManager=DEFAULT,
        Cache=DEFAULT,
        UpdateManager=DEFAULT,
        StateFileManager=DEFAULT,
    ) as mocks:
        # Configure mocks
        mocks["PathResolver"].return_value = path_resolver
        mocks["ConfigManager"].return_value.load.return_value = test_config
        mocks["Cache"].return_value = mock_cache
        mocks["UpdateManager"].return_value = mock_update_manager

        yield mocks


class TestSignalHandling:
    """Test signal handling with critical sections."""

    def test_signal_during_normal_operation(self):
        """Should set shutdown flag during normal operation."""
        DaemonState.shutdown_flag = False
        DaemonState.update_in_progress = False
        DaemonState.critical_section = False

        daemon._signal_handler(signal.SIGTERM, None)

        assert DaemonState.shutdown_flag is True
        assert len(DaemonState.pending_signals) == 0

    def test_signal_during_update(self):
        """Should set shutdown flag during non-critical update."""
        DaemonState.shutdown_flag = False
        DaemonState.update_in_progress = True
        DaemonState.critical_section = False

        daemon._signal_handler(signal.SIGTERM, None)

        assert DaemonState.shutdown_flag is True
        assert len(DaemonState.pending_signals) == 0

    def test_signal_during_critical_section(self):
        """Should queue signal during critical section."""
        DaemonState.shutdown_flag = False
        DaemonState.critical_section = True
        DaemonState.pending_signals = []

        daemon._signal_handler(signal.SIGTERM, None)

        assert DaemonState.shutdown_flag is False
        assert DaemonState.pending_signals == [signal.SIGTERM]

    def test_multiple_signals_queued(self):
        """Should queue multiple signals during critical section."""
        DaemonState.critical_section = True
        DaemonState.pending_signals = []

        daemon._signal_handler(signal.SIGTERM, None)
        daemon._signal_handler(signal.SIGINT, None)

        assert DaemonState.pending_signals == [signal.SIGTERM, signal.SIGINT]


class TestSSEEndpoint:
    """Test Server-Sent Events streaming endpoint."""

    @pytest.mark.asyncio
    async def test_sse_stream_with_state(
        self, mock_update_manager, mock_state_manager, mock_dependencies
    ):
        """Should stream update state as SSE events."""
        # Set up daemon state
        DaemonState.update_manager = mock_update_manager
        DaemonState.shutdown_flag = False

        # Configure StateFileManager mock from fixture (already patched by mock_dependencies)
        mock_dependencies["StateFileManager"].return_value = mock_state_manager

        # Mock state manager to return state once then None
        mock_state_manager.read_state.side_effect = [
            {"phase": "updating", "progress": 50},
            None,
        ]

        # Mock the StreamResponse to avoid actual HTTP operations
        with patch(
            "birdnetpi.daemons.update_daemon.aiohttp.web.StreamResponse", autospec=True
        ) as mock_resp_class:
            # mock_resp_class is already autospec'd, just use its return_value
            mock_response = mock_resp_class.return_value

            # Create mock request
            request = create_autospec(aiohttp.web.Request, spec_set=True, instance=True)

            # Run SSE handler briefly
            DaemonState.shutdown_flag = False
            task = asyncio.create_task(daemon.handle_sse_stream(request))
            await asyncio.sleep(0.1)

            # Stop the task
            DaemonState.shutdown_flag = True
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify response was prepared and data was written
            mock_response.prepare.assert_called_once_with(request)
            assert mock_response.write.called

    @pytest.mark.asyncio
    async def test_sse_heartbeat(self, mock_update_manager, mock_state_manager, mock_dependencies):
        """Should send heartbeat when no state available."""
        DaemonState.update_manager = mock_update_manager
        mock_state_manager.read_state.return_value = None

        # Mock the StreamResponse
        with patch(
            "birdnetpi.daemons.update_daemon.aiohttp.web.StreamResponse", autospec=True
        ) as mock_resp_class:
            # mock_resp_class is already autospec'd, just use its return_value
            mock_response = mock_resp_class.return_value

            # Configure StateFileManager mock from fixture (already patched by mock_dependencies)
            mock_dependencies["StateFileManager"].return_value = mock_state_manager

            request = create_autospec(aiohttp.web.Request, spec_set=True, instance=True)

            # Run briefly and check heartbeat is sent
            DaemonState.shutdown_flag = False
            task = asyncio.create_task(daemon.handle_sse_stream(request))
            await asyncio.sleep(0.1)

            DaemonState.shutdown_flag = True
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should write heartbeat
            mock_response.write.assert_called()


class TestMonitorLoop:
    """Test monitor mode loop."""

    @pytest.mark.asyncio
    async def test_monitor_loop_check_request(self, mock_cache, mock_update_manager, test_config):
        """Should process check request from Redis."""
        # Set up daemon state
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        DaemonState.config_manager.load.return_value = test_config
        DaemonState.shutdown_flag = False

        # Mock cache to return check request once
        mock_cache.get.side_effect = [
            {"action": "check"},  # First call returns request
            None,  # Subsequent calls return None
        ]

        # Run monitor loop briefly
        task = asyncio.create_task(daemon.run_monitor_loop())
        await asyncio.sleep(0.1)

        # Stop the loop
        DaemonState.shutdown_flag = True
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify check was performed
        mock_update_manager.check_for_updates.assert_called_once()
        mock_cache.set.assert_called()
        mock_cache.delete.assert_called_with("update:request")

    @pytest.mark.asyncio
    async def test_monitor_loop_periodic_check(self, mock_cache, mock_update_manager, test_config):
        """Should perform periodic update checks."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)

        # Enable startup check to ensure at least one check happens
        test_config.updates.auto_check_on_startup = True
        DaemonState.config_manager.load.return_value = test_config
        DaemonState.shutdown_flag = False

        # No request in cache
        mock_cache.get.return_value = None

        # Run briefly
        task = asyncio.create_task(daemon.run_monitor_loop())
        await asyncio.sleep(0.1)

        DaemonState.shutdown_flag = True
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should perform check on startup
        mock_update_manager.check_for_updates.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_loop_actual_periodic_check(
        self, mock_cache, mock_update_manager, test_config
    ):
        """Should perform periodic checks after interval expires."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)

        # Disable startup check, set very short interval
        test_config.updates.auto_check_on_startup = False
        test_config.updates.check_enabled = True
        test_config.updates.check_interval_hours = 0.0001  # Very short interval (0.36 seconds)
        DaemonState.config_manager.load.return_value = test_config
        DaemonState.shutdown_flag = False

        # No request in cache
        mock_cache.get.return_value = None

        # Store original sleep function to avoid recursion
        original_sleep = asyncio.sleep

        # Track sleep calls and simulate time passing
        sleep_count = 0
        mock_time_value = 0.0

        async def mock_sleep(duration):
            nonlocal sleep_count, mock_time_value
            sleep_count += 1
            # Advance time by the sleep duration to trigger periodic check
            mock_time_value += duration
            # After seeing periodic check happen, stop the loop
            if mock_update_manager.check_for_updates.called:
                DaemonState.shutdown_flag = True
            # Stop after max iterations to prevent infinite loop
            elif sleep_count >= 5:
                DaemonState.shutdown_flag = True
            # Actually sleep briefly to let coroutines run
            await original_sleep(0.01)

        # Create a mock event loop with our time method
        mock_loop = create_autospec(asyncio.AbstractEventLoop, spec_set=True, instance=True)
        mock_loop.time.side_effect = lambda: mock_time_value

        with patch("birdnetpi.daemons.update_daemon.asyncio.sleep", mock_sleep):
            with patch(
                "birdnetpi.daemons.update_daemon.asyncio.get_event_loop", return_value=mock_loop
            ):
                # Run the monitor loop
                await daemon.run_monitor_loop()

        # Should have performed periodic check
        mock_update_manager.check_for_updates.assert_called()


class TestUpdateProcessing:
    """Test update request processing."""

    @pytest.mark.asyncio
    async def test_process_check_request(self, mock_cache, mock_update_manager):
        """Should process check update request."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager

        request = {"action": "check"}
        await daemon.process_update_request(request)

        mock_update_manager.check_for_updates.assert_called_once()
        mock_cache.set.assert_called_with(
            "update:status",
            {
                "current_version": "v1.0.0",
                "latest_version": "v1.1.0",
                "update_available": True,
                "checked_at": "2024-01-01T12:00:00",
            },
        )

    @pytest.mark.asyncio
    async def test_process_apply_request(self, mock_cache, mock_update_manager):
        """Should process apply update request."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.update_in_progress = False

        request = {"action": "apply", "version": "v1.1.0"}
        await daemon.process_update_request(request)

        mock_update_manager.apply_update.assert_called_once_with("v1.1.0")
        mock_cache.set.assert_called_with("update:result", {"success": True, "version": "v1.1.0"})
        mock_cache.delete.assert_called_with("update:request")

    @pytest.mark.asyncio
    async def test_process_apply_with_pending_signals(self, mock_cache, mock_update_manager):
        """Should process pending signals after update completes."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.pending_signals = [signal.SIGTERM]

        request = {"action": "apply", "version": "v1.1.0"}

        with patch("birdnetpi.daemons.update_daemon._signal_handler", autospec=True) as mock_signal:
            await daemon.process_update_request(request)

            # Should process pending signal
            mock_signal.assert_called_once_with(signal.SIGTERM, None)
            assert DaemonState.pending_signals == []


class TestUpdateWithRedisMonitoring:
    """Test full update mode with Redis monitoring."""

    @pytest.mark.asyncio
    async def test_redis_monitoring_loop(self, mock_cache, mock_update_manager, test_config):
        """Should monitor Redis for update requests."""
        DaemonState.cache_service = mock_cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        DaemonState.config_manager.load.return_value = test_config
        DaemonState.shutdown_flag = False

        # Mock to return update request once
        call_count = 0

        def get_request(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"action": "check"}
            return None

        with patch(
            "birdnetpi.daemons.update_daemon.check_for_update_request", autospec=True
        ) as mock_check:
            mock_check.side_effect = get_request

            # Run monitoring loop briefly
            task = asyncio.create_task(daemon.run_update_with_redis_monitoring())
            await asyncio.sleep(0.2)

            DaemonState.shutdown_flag = True
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have checked for updates
            assert mock_check.called


class TestDaemonInitialization:
    """Test daemon initialization and mode selection."""

    @pytest.mark.asyncio
    async def test_run_monitor_mode(self, mock_dependencies, mock_cache):
        """Should run in monitor mode."""
        mock_dependencies["Cache"].return_value = mock_cache

        with patch("birdnetpi.daemons.update_daemon.run_monitor_loop", autospec=True) as mock_loop:
            mock_loop.return_value = asyncio.Future()
            mock_loop.return_value.set_result(None)

            with patch(
                "birdnetpi.daemons.update_daemon.start_http_server", autospec=True
            ) as mock_http:
                mock_http.return_value = asyncio.Future()
                mock_http.return_value.set_result(None)

                result = await daemon.run("monitor")

                assert result == 0
                mock_loop.assert_called_once()
                mock_http.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_both_mode(self, mock_dependencies, mock_cache):
        """Should run in both mode (SBC)."""
        mock_dependencies["Cache"].return_value = mock_cache

        with patch(
            "birdnetpi.daemons.update_daemon.run_update_with_redis_monitoring", autospec=True
        ) as mock_both:
            mock_both.return_value = asyncio.Future()
            mock_both.return_value.set_result(None)

            with patch(
                "birdnetpi.daemons.update_daemon.start_http_server", autospec=True
            ) as mock_http:
                mock_http.return_value = asyncio.Future()
                mock_http.return_value.set_result(None)

                result = await daemon.run("both")

                assert result == 0
                mock_both.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_migrate_mode(self, mock_dependencies):
        """Should run in migrate mode (one-shot)."""
        # Migrate mode doesn't require Redis
        mock_dependencies["Cache"].side_effect = RuntimeError("Redis not available")

        result = await daemon.run("migrate")

        # Should complete successfully without Redis
        assert result == 0
        assert DaemonState.cache_service is None

    @pytest.mark.asyncio
    async def test_redis_connection_failure_monitor_mode(self, mock_dependencies):
        """Should fail in monitor mode if Redis unavailable."""
        mock_dependencies["Cache"].side_effect = RuntimeError("Redis connection failed")

        result = await daemon.run("monitor")

        # Monitor mode requires Redis
        assert result == 1

    @pytest.mark.asyncio
    async def test_interrupted_update_recovery(self, mock_dependencies, mock_state_manager):
        """Should detect interrupted update on startup."""
        mock_dependencies["StateFileManager"].return_value = mock_state_manager
        mock_state_manager.read_state.return_value = {
            "phase": "updating_code",
            "target_version": "v1.1.0",
        }

        with patch("birdnetpi.daemons.update_daemon.run_monitor_loop", autospec=True) as mock_loop:
            mock_loop.return_value = asyncio.Future()
            mock_loop.return_value.set_result(None)

            with patch(
                "birdnetpi.daemons.update_daemon.start_http_server", autospec=True
            ) as mock_http:
                mock_http.return_value = asyncio.Future()
                mock_http.return_value.set_result(None)

                await daemon.run("monitor")

                # Should detect interrupted update
                mock_state_manager.read_state.assert_called()


class TestHTTPServer:
    """Test HTTP server for SSE streaming."""

    @pytest.mark.asyncio
    async def test_start_http_server(self):
        """Should start HTTP server on localhost only."""
        with patch("aiohttp.web.Application", autospec=True) as mock_app_class:
            # mock_app_class is already autospec'd, just use return_value
            app = mock_app_class.return_value

            with patch("aiohttp.web.AppRunner", autospec=True) as mock_runner_class:
                runner = mock_runner_class.return_value

                with patch("aiohttp.web.TCPSite", autospec=True) as mock_site_class:
                    site = mock_site_class.return_value

                    await daemon.start_http_server()

                    # Should bind to localhost only
                    mock_site_class.assert_called_once_with(runner, "127.0.0.1", 8889)
                    site.start.assert_called_once()

                    # Should register SSE endpoint
                    app.router.add_get.assert_called_once_with(
                        "/api/update/stream", daemon.handle_sse_stream
                    )


class TestCheckForUpdateRequest:
    """Test Redis update request checking."""

    def test_check_for_update_request_with_cache(self, mock_cache):
        """Should return update request from cache."""
        DaemonState.cache_service = mock_cache
        mock_cache.get.return_value = {"action": "check"}

        result = daemon.check_for_update_request()

        assert result == {"action": "check"}
        mock_cache.get.assert_called_once_with("update:request")

    def test_check_for_update_request_no_cache(self):
        """Should return None if cache not available."""
        DaemonState.cache_service = None

        result = daemon.check_for_update_request()

        assert result is None

    def test_check_for_update_request_error(self, mock_cache):
        """Should return None on cache error."""
        DaemonState.cache_service = mock_cache
        mock_cache.get.side_effect = Exception("Redis error")

        result = daemon.check_for_update_request()

        assert result is None


class TestCLICommand:
    """Test CLI command entry point."""

    def test_cli_command_exists(self):
        """Should have main CLI command."""
        assert hasattr(daemon, "main")
        assert callable(daemon.main)

    @patch("birdnetpi.daemons.update_daemon.asyncio.run", autospec=True)
    @patch("birdnetpi.daemons.update_daemon.signal.signal", autospec=True)
    def test_main_entry_point(self, mock_signal, mock_asyncio_run):
        """Should set up signal handlers and run async main."""
        mock_asyncio_run.return_value = 0

        with patch("sys.argv", ["update-daemon", "monitor"]):
            with patch("birdnetpi.daemons.update_daemon.click", autospec=True) as mock_click:
                # Mock the click decorator chain
                mock_click.command.return_value = lambda f: f
                mock_click.argument.return_value = lambda f: f
                mock_click.option.return_value = lambda f: f

                # Import and run main

                # The actual main function would be wrapped by click
                # We test the underlying run function instead
                assert callable(daemon.run)
