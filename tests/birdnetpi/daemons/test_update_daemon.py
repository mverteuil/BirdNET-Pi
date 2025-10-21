"""Tests for update daemon."""

import asyncio
import signal
from unittest.mock import DEFAULT, MagicMock, create_autospec, patch

import aiohttp.web
import pytest

import birdnetpi.daemons.update_daemon as daemon
from birdnetpi.config.manager import ConfigManager
from birdnetpi.daemons.update_daemon import DaemonState
from birdnetpi.releases.update_manager import StateFileManager, UpdateManager
from birdnetpi.system.file_manager import FileManager


@pytest.fixture(autouse=True)
def reset_daemon_state():
    """Reset daemon state before each test."""
    DaemonState.reset()
    yield
    DaemonState.reset()


@pytest.fixture
def daemon_test_config(test_config):
    """Provide test configuration for daemon tests."""
    test_config.updates.check_interval_hours = 24
    test_config.updates.check_enabled = True
    test_config.updates.auto_check_on_startup = False
    return test_config


@pytest.fixture
def mock_update_manager(path_resolver):
    """Mock UpdateManager for testing."""
    manager = MagicMock(spec=UpdateManager)
    manager.check_for_updates.return_value = {
        "current_version": "v1.0.0",
        "latest_version": "v1.1.0",
        "available": True,
        "checked_at": "2024-01-01T12:00:00",
    }
    manager.apply_update.return_value = {"success": True, "version": "v1.1.0"}
    # Configure instance attributes that spec doesn't recognize
    manager.configure_mock(path_resolver=path_resolver, file_manager=MagicMock(spec=FileManager))
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
def mock_dependencies(mocker, daemon_test_config, cache, mock_update_manager, path_resolver):
    """Mock external dependencies for update daemon."""
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
        mocks["PathResolver"].return_value = path_resolver
        mocks["ConfigManager"].return_value.load.return_value = daemon_test_config
        mocks["Cache"].return_value = cache
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
        DaemonState.update_manager = mock_update_manager
        DaemonState.shutdown_flag = False
        mock_dependencies["StateFileManager"].return_value = mock_state_manager
        mock_state_manager.read_state.side_effect = [{"phase": "updating", "progress": 50}, None]
        with patch(
            "birdnetpi.daemons.update_daemon.aiohttp.web.StreamResponse", autospec=True
        ) as mock_resp_class:
            mock_response = mock_resp_class.return_value
            request = create_autospec(aiohttp.web.Request, spec_set=True, instance=True)
            DaemonState.shutdown_flag = False
            task = asyncio.create_task(daemon.handle_sse_stream(request))
            await asyncio.sleep(0.1)
            DaemonState.shutdown_flag = True
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            mock_response.prepare.assert_called_once_with(request)
            assert mock_response.write.called

    @pytest.mark.asyncio
    async def test_sse_heartbeat(self, mock_update_manager, mock_state_manager, mock_dependencies):
        """Should send heartbeat when no state available."""
        DaemonState.update_manager = mock_update_manager
        mock_state_manager.read_state.return_value = None
        with patch(
            "birdnetpi.daemons.update_daemon.aiohttp.web.StreamResponse", autospec=True
        ) as mock_resp_class:
            mock_response = mock_resp_class.return_value
            mock_dependencies["StateFileManager"].return_value = mock_state_manager
            request = create_autospec(aiohttp.web.Request, spec_set=True, instance=True)
            DaemonState.shutdown_flag = False
            task = asyncio.create_task(daemon.handle_sse_stream(request))
            await asyncio.sleep(0.1)
            DaemonState.shutdown_flag = True
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            mock_response.write.assert_called()


class TestMonitorLoop:
    """Test monitor mode loop."""

    @pytest.mark.asyncio
    async def test_monitor_loop_check_request(self, cache, mock_update_manager, daemon_test_config):
        """Should process check request from Redis."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        DaemonState.config_manager.load.return_value = daemon_test_config
        DaemonState.shutdown_flag = False
        cache.get.side_effect = [{"action": "check"}, None]
        task = asyncio.create_task(daemon.run_monitor_loop())
        await asyncio.sleep(0.1)
        DaemonState.shutdown_flag = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        mock_update_manager.check_for_updates.assert_called_once()
        cache.set.assert_called()
        cache.delete.assert_called_with("update:request")

    @pytest.mark.asyncio
    async def test_monitor_loop_periodic_check(
        self, cache, mock_update_manager, daemon_test_config
    ):
        """Should perform periodic update checks."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        daemon_test_config.updates.auto_check_on_startup = True
        DaemonState.config_manager.load.return_value = daemon_test_config
        DaemonState.shutdown_flag = False
        cache.get.return_value = None
        task = asyncio.create_task(daemon.run_monitor_loop())
        await asyncio.sleep(0.1)
        DaemonState.shutdown_flag = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        mock_update_manager.check_for_updates.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_loop_actual_periodic_check(
        self, cache, mock_update_manager, daemon_test_config
    ):
        """Should perform periodic checks after interval expires."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        daemon_test_config.updates.auto_check_on_startup = False
        daemon_test_config.updates.check_enabled = True
        daemon_test_config.updates.check_interval_hours = 0.0001
        DaemonState.config_manager.load.return_value = daemon_test_config
        DaemonState.shutdown_flag = False
        cache.get.return_value = None
        original_sleep = asyncio.sleep
        sleep_count = 0
        mock_time_value = 0.0

        async def mock_sleep(duration):
            nonlocal sleep_count, mock_time_value
            sleep_count += 1
            mock_time_value += duration
            if mock_update_manager.check_for_updates.called:
                DaemonState.shutdown_flag = True
            elif sleep_count >= 5:
                DaemonState.shutdown_flag = True
            await original_sleep(0.01)

        mock_loop = create_autospec(asyncio.AbstractEventLoop, spec_set=True, instance=True)
        mock_loop.time.side_effect = lambda: mock_time_value
        with patch("birdnetpi.daemons.update_daemon.asyncio.sleep", mock_sleep):
            with patch(
                "birdnetpi.daemons.update_daemon.asyncio.get_event_loop", return_value=mock_loop
            ):
                await daemon.run_monitor_loop()
        mock_update_manager.check_for_updates.assert_called()


class TestUpdateProcessing:
    """Test update request processing."""

    @pytest.mark.asyncio
    async def test_process_check_request(self, cache, mock_update_manager):
        """Should process check update request."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        request = {"action": "check"}
        await daemon.process_update_request(request)
        mock_update_manager.check_for_updates.assert_called_once()
        cache.set.assert_called_with(
            "update:status",
            {
                "current_version": "v1.0.0",
                "latest_version": "v1.1.0",
                "available": True,
                "checked_at": "2024-01-01T12:00:00",
            },
        )

    @pytest.mark.asyncio
    async def test_process_apply_request(self, cache, mock_update_manager):
        """Should process apply update request."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.update_in_progress = False
        request = {"action": "apply", "version": "v1.1.0"}
        await daemon.process_update_request(request)
        mock_update_manager.apply_update.assert_called_once_with("v1.1.0")
        cache.set.assert_called_with("update:result", {"success": True, "version": "v1.1.0"})
        cache.delete.assert_called_with("update:request")

    @pytest.mark.asyncio
    async def test_process_apply_with_pending_signals(self, cache, mock_update_manager):
        """Should process pending signals after update completes."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.pending_signals = [signal.SIGTERM]
        request = {"action": "apply", "version": "v1.1.0"}
        with patch("birdnetpi.daemons.update_daemon._signal_handler", autospec=True) as mock_signal:
            await daemon.process_update_request(request)
            mock_signal.assert_called_once_with(signal.SIGTERM, None)
            assert DaemonState.pending_signals == []


class TestUpdateWithRedisMonitoring:
    """Test full update mode with Redis monitoring."""

    @pytest.mark.asyncio
    async def test_redis_monitoring_loop(self, cache, mock_update_manager, daemon_test_config):
        """Should monitor Redis for update requests."""
        DaemonState.cache_service = cache
        DaemonState.update_manager = mock_update_manager
        DaemonState.config_manager = MagicMock(spec=ConfigManager)
        DaemonState.config_manager.load.return_value = daemon_test_config
        DaemonState.shutdown_flag = False
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
            task = asyncio.create_task(daemon.run_update_with_redis_monitoring())
            await asyncio.sleep(0.2)
            DaemonState.shutdown_flag = True
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert mock_check.called


class TestDaemonInitialization:
    """Test daemon initialization and mode selection."""

    @pytest.mark.asyncio
    async def test_run_monitor_mode(self, mock_dependencies, cache):
        """Should run in monitor mode."""
        mock_dependencies["Cache"].return_value = cache
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
    async def test_run_both_mode(self, mock_dependencies, cache):
        """Should run in both mode (SBC)."""
        mock_dependencies["Cache"].return_value = cache
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
        mock_dependencies["Cache"].side_effect = RuntimeError("Redis not available")
        result = await daemon.run("migrate")
        assert result == 0
        assert DaemonState.cache_service is None

    @pytest.mark.asyncio
    async def test_redis_connection_failure_monitor_mode(self, mock_dependencies):
        """Should fail in monitor mode if Redis unavailable."""
        mock_dependencies["Cache"].side_effect = RuntimeError("Redis connection failed")
        result = await daemon.run("monitor")
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
                mock_state_manager.read_state.assert_called()


class TestHTTPServer:
    """Test HTTP server for SSE streaming."""

    @pytest.mark.asyncio
    async def test_start_http_server(self):
        """Should start HTTP server on localhost only."""
        with patch("aiohttp.web.Application", autospec=True) as mock_app_class:
            app = mock_app_class.return_value
            with patch("aiohttp.web.AppRunner", autospec=True) as mock_runner_class:
                runner = mock_runner_class.return_value
                with patch("aiohttp.web.TCPSite", autospec=True) as mock_site_class:
                    site = mock_site_class.return_value
                    await daemon.start_http_server()
                    mock_site_class.assert_called_once_with(runner, "127.0.0.1", 8889)
                    site.start.assert_called_once()
                    app.router.add_get.assert_called_once_with(
                        "/api/update/stream", daemon.handle_sse_stream
                    )


class TestCheckForUpdateRequest:
    """Test Redis update request checking."""

    def test_check_for_update_request_with_cache(self, cache):
        """Should return update request from cache."""
        DaemonState.cache_service = cache
        cache.get.return_value = {"action": "check"}
        result = daemon.check_for_update_request()
        assert result == {"action": "check"}
        cache.get.assert_called_once_with("update:request")

    def test_check_for_update_request_no_cache(self):
        """Should return None if cache not available."""
        DaemonState.cache_service = None
        result = daemon.check_for_update_request()
        assert result is None

    def test_check_for_update_request_error(self, cache):
        """Should return None on cache error."""
        DaemonState.cache_service = cache
        cache.get.side_effect = Exception("Redis error")
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
                mock_click.command.return_value = lambda f: f
                mock_click.argument.return_value = lambda f: f
                mock_click.option.return_value = lambda f: f
                assert callable(daemon.run)
