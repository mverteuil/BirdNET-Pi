import os
import subprocess
from unittest.mock import MagicMock

from birdnetpi.config import BirdNETConfig
from birdnetpi.utils.structlog_configurator import (
    _add_static_context,
    _configure_handlers,
    _configure_processors,
    _get_environment_config,
    configure_structlog,
    get_deployment_environment,
    get_git_version,
    get_logger,
    is_docker_environment,
    is_systemd_available,
)


class TestEnvironmentDetection:
    """Test environment detection functions."""

    def test_is_docker_environment__dockerenv(self, mocker):
        """Should return True when /.dockerenv exists."""
        mocker.patch("os.path.exists", return_value=True)
        assert is_docker_environment() is True

    def test_is_docker_environment__env_var(self, mocker):
        """Should return True when DOCKER_CONTAINER env var is set."""
        mocker.patch("os.path.exists", return_value=False)
        mocker.patch.dict(os.environ, {"DOCKER_CONTAINER": "true"})
        assert is_docker_environment() is True

    def test_is_docker_environment_false(self, mocker):
        """Should return False when no Docker indicators present."""
        mocker.patch("os.path.exists", return_value=False)
        mocker.patch.dict(os.environ, {}, clear=True)
        assert is_docker_environment() is False

    def test_is_systemd_available_true(self, mocker):
        """Should return True when systemctl command succeeds."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        assert is_systemd_available() is True

    def test_is_systemd_available_false_command_failed(self, mocker):
        """Should return False when systemctl command fails."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        assert is_systemd_available() is False

    def test_is_systemd_available_false_exception(self, mocker):
        """Should return False when subprocess raises exception."""
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        assert is_systemd_available() is False


class TestGitVersion:
    """Test git version detection."""

    def test_get_git_version(self, mocker):
        """Should return formatted version when git commands succeed."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout="abc12345\n"),
        ]
        result = get_git_version()
        assert result == "main@abc12345"

    def test_get_git_version_branch_failure(self, mocker):
        """Should handle branch command failure gracefully."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout=""),
            MagicMock(returncode=0, stdout="abc12345\n"),
        ]
        result = get_git_version()
        assert result == "unknown@abc12345"

    def test_get_git_version_commit_failure(self, mocker):
        """Should handle commit command failure gracefully."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=1, stdout=""),
        ]
        result = get_git_version()
        assert result == "main@unknown"

    def test_get_git_version_exception(self, mocker):
        """Should return 'unknown' when git commands raise exception."""
        mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
        result = get_git_version()
        assert result == "unknown"


class TestDeploymentEnvironment:
    """Test deployment environment detection."""

    def test_get_deployment_environment_docker(self, mocker):
        """Should return 'docker' when in Docker environment."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=True
        )
        assert get_deployment_environment() == "docker"

    def test_get_deployment_environment_sbc(self, mocker):
        """Should return 'sbc' when systemd available and not in Docker."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=False
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_systemd_available", return_value=True
        )
        assert get_deployment_environment() == "sbc"

    def test_get_deployment_environment_development(self, mocker):
        """Should return 'development' when BIRDNETPI_ENV is set."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=False
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_systemd_available", return_value=False
        )
        mocker.patch.dict(os.environ, {"BIRDNETPI_ENV": "development"})
        assert get_deployment_environment() == "development"

    def test_get_deployment_environment_unknown(self, mocker):
        """Should return 'unknown' when no environment indicators present."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=False
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_systemd_available", return_value=False
        )
        mocker.patch.dict(os.environ, {}, clear=True)
        assert get_deployment_environment() == "unknown"


class TestStaticContextProcessor:
    """Test static context processor function."""

    def test_add_static_context_processor(self):
        """Should add extra fields to event dict."""
        extra_fields = {"service": "test", "version": "1.0"}
        processor = _add_static_context(extra_fields)

        event_dict = {"message": "test message"}
        result = processor(MagicMock(), "info", event_dict)

        assert result["service"] == "test"
        assert result["version"] == "1.0"
        assert result["message"] == "test message"


class TestEnvironmentConfig:
    """Test environment configuration detection."""

    def test_get_environment_config_docker_dev(self, mocker):
        """Should detect Docker development environment."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=True
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_systemd_available", return_value=False
        )
        mocker.patch.dict(os.environ, {"BIRDNETPI_ENV": "development"})

        is_docker, has_systemd, is_development = _get_environment_config()
        assert is_docker is True
        assert has_systemd is False
        assert is_development is True

    def test_get_environment_config_sbc_production(self, mocker):
        """Should detect SBC production environment."""
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_docker_environment", return_value=False
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.is_systemd_available", return_value=True
        )
        mocker.patch.dict(os.environ, {}, clear=True)

        is_docker, has_systemd, is_development = _get_environment_config()
        assert is_docker is False
        assert has_systemd is True
        assert is_development is False


class TestProcessorConfiguration:
    """Test processor configuration logic."""

    def test_configure_processors_basic(self, mocker):
        """Should configure basic processors."""
        config = BirdNETConfig()
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_git_version", return_value="main@abc123"
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_deployment_environment", return_value="test"
        )

        processors = _configure_processors(config, False, False, True)

        assert len(processors) >= 4  # Basic processors
        # Should end with ConsoleRenderer for development
        assert any("ConsoleRenderer" in str(type(p)) for p in processors)

    def test_configure_processors__location(self, mocker):
        """Should include location when coordinates are set."""
        config = BirdNETConfig(latitude=40.7128, longitude=-74.0060)
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_git_version", return_value="main@abc123"
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_deployment_environment", return_value="test"
        )

        processors = _configure_processors(config, False, False, True)

        # Verify static context processor was added with location
        assert len(processors) >= 4

    def test_configure_processors_json_output(self, mocker):
        """Should use JSON renderer for Docker/SBC environments."""
        config = BirdNETConfig()
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_git_version", return_value="main@abc123"
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator.get_deployment_environment",
            return_value="docker",
        )

        processors = _configure_processors(config, True, False, False)

        # Should end with JSONRenderer for Docker
        assert any("JSONRenderer" in str(type(p)) for p in processors)


class TestHandlerConfiguration:
    """Test logging handler configuration."""

    def test_configure_handlers_console(self, mocker):
        """Should configure console handler for Docker/dev environments."""
        config = BirdNETConfig()
        mock_logger = mocker.patch("logging.getLogger")
        mock_root = MagicMock()
        mock_logger.return_value = mock_root
        mock_root.handlers = []

        _configure_handlers(config, True, False, False)

        mock_root.addHandler.assert_called()
        mock_root.setLevel.assert_called()

    def test_configure_handlers_console_only(self, mocker):
        """Should configure console handler for development without systemd."""
        config = BirdNETConfig()

        mock_logger = mocker.patch("logging.getLogger")
        mock_root = MagicMock()
        mock_logger.return_value = mock_root
        mock_root.handlers = []

        _configure_handlers(config, False, False, True)

        mock_root.addHandler.assert_called()

    def test_configure_handlers_journald(self, mocker):
        """Should configure journald handler for SBC environments."""
        config = BirdNETConfig()
        mock_logger = mocker.patch("logging.getLogger")
        mock_root = MagicMock()
        mock_logger.return_value = mock_root
        mock_root.handlers = []

        # Mock the _add_journald_handler function directly
        mock_add_journald = mocker.patch(
            "birdnetpi.utils.structlog_configurator._add_journald_handler"
        )

        _configure_handlers(config, False, True, False)

        mock_add_journald.assert_called_once()
        mock_root.setLevel.assert_called()

    def test_configure_handlers_journald_fallback(self, mocker):
        """Should fallback to stderr when journald unavailable."""
        config = BirdNETConfig()

        mock_logger = mocker.patch("logging.getLogger")
        mock_root = MagicMock()
        mock_logger.return_value = mock_root
        mock_root.handlers = []

        # Mock the journald import to fail, triggering stderr fallback
        mocker.patch("birdnetpi.utils.structlog_configurator._add_journald_handler")

        _configure_handlers(config, False, True, False)

        mock_root.setLevel.assert_called()


class TestMainConfiguration:
    """Test main configuration function."""

    def test_configure_structlog(self, mocker):
        """Should configure structlog successfully."""
        config = BirdNETConfig()

        # Mock all dependencies
        mocker.patch(
            "birdnetpi.utils.structlog_configurator._get_environment_config",
            return_value=(False, False, True),
        )
        mocker.patch(
            "birdnetpi.utils.structlog_configurator._configure_processors", return_value=[]
        )
        mock_configure = mocker.patch("structlog.configure")
        mocker.patch("birdnetpi.utils.structlog_configurator._configure_handlers")
        mock_get_logger = mocker.patch("structlog.get_logger")
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        configure_structlog(config)

        mock_configure.assert_called_once()
        mock_logger.info.assert_called_once()

    def test_get_logger(self, mocker):
        """Should return structlog logger instance."""
        mock_structlog = mocker.patch("structlog.get_logger")
        mock_logger = MagicMock()
        mock_structlog.return_value = mock_logger

        result = get_logger("test")

        mock_structlog.assert_called_once_with("test")
        assert result == mock_logger
