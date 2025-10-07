"""Tests for the structlog configurator module."""

import logging
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
import structlog

from birdnetpi.config import BirdNETConfig
from birdnetpi.config.models import LoggingConfig
from birdnetpi.system.structlog_configurator import (
    _add_journald_handler,
    _add_static_context,
    _configure_handlers,
    _configure_processors,
    _get_environment_config,
    configure_structlog,
)


class TestAddStaticContext:
    """Test the _add_static_context processor."""

    def test_adds_static_fields_to_event_dict(self):
        """Should add static fields to all log events."""
        extra_fields = {"service": "test", "version": "1.0.0"}
        processor = _add_static_context(extra_fields)

        # Mock logger and event dict
        logger = Mock(spec=structlog.BoundLogger)
        event_dict = {"event": "test_event", "level": "info"}

        # Process the event
        result = processor(logger, "info", event_dict)

        # Check fields were added
        assert result["service"] == "test"
        assert result["version"] == "1.0.0"
        assert result["event"] == "test_event"  # Original fields preserved

    def test_overwrites_existing_fields(self):
        """Should overwrite existing fields with static values."""
        extra_fields = {"service": "override"}
        processor = _add_static_context(extra_fields)

        # Event dict with existing service field
        event_dict = {"event": "test", "service": "original"}

        result = processor(Mock(spec=structlog.BoundLogger), "info", event_dict)

        # Static field should override
        assert result["service"] == "override"

    def test_empty_extra_fields(self):
        """Should handle empty extra fields gracefully."""
        processor = _add_static_context({})
        event_dict = {"event": "test"}

        result = processor(Mock(spec=structlog.BoundLogger), "info", event_dict)

        # Original dict unchanged
        assert result == {"event": "test"}


class TestGetEnvironmentConfig:
    """Test environment detection."""

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_detects_docker_environment(self, mock_utils):
        """Should correctly identify Docker environment."""
        mock_utils.is_docker_environment.return_value = True
        mock_utils.is_systemd_available.return_value = False

        is_docker, has_systemd, is_development = _get_environment_config()

        assert is_docker is True
        assert has_systemd is False
        assert is_development is False

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {"BIRDNETPI_ENV": "development"})
    def test_detects_development_environment(self, mock_utils):
        """Should correctly identify development environment."""
        mock_utils.is_docker_environment.return_value = False
        mock_utils.is_systemd_available.return_value = False

        is_docker, has_systemd, is_development = _get_environment_config()

        assert is_docker is False
        assert has_systemd is False
        assert is_development is True

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_detects_systemd_environment(self, mock_utils):
        """Should correctly identify systemd availability."""
        mock_utils.is_docker_environment.return_value = False
        mock_utils.is_systemd_available.return_value = True

        is_docker, has_systemd, is_development = _get_environment_config()

        assert is_docker is False
        assert has_systemd is True
        assert is_development is False


class TestConfigureProcessors:
    """Test processor configuration."""

    @pytest.fixture
    def test_config(self, test_config):
        """Should create a mock BirdNET config."""
        test_config.logging = LoggingConfig(
            level="info",
            json_logs=None,
            include_caller=False,
            extra_fields={},
        )
        test_config.site_name = "Test Site"
        test_config.latitude = 45.5
        test_config.longitude = -73.6
        return test_config

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {}, clear=True)
    def test_basic_processor_configuration(self, mock_utils, test_config):
        """Should configure basic processors."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"

        processors, use_json = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Should have standard processors
        assert len(processors) >= 6  # Basic processors + wrap_for_formatter
        # Last processor should be wrap_for_formatter
        assert processors[-1] == structlog.stdlib.ProcessorFormatter.wrap_for_formatter
        # JSON should be False for non-Docker, non-systemd
        assert use_json is False

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_includes_caller_when_configured(self, mock_utils, test_config):
        """Should include caller info when configured."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"
        test_config.logging.include_caller = True

        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Should have CallsiteParameterAdder
        processor_types = [type(p).__name__ for p in processors if hasattr(type(p), "__name__")]
        assert "CallsiteParameterAdder" in processor_types

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {"SERVICE_NAME": "custom-service"})
    def test_uses_service_name_from_environment(self, mock_utils, test_config):
        """Should use SERVICE_NAME from environment if available."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"
        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Find the static context processor
        for processor in processors:
            if hasattr(processor, "__name__") and "processor" in processor.__name__:
                # This is our wrapped processor function
                test_dict = {}
                result = processor(Mock(spec=structlog.BoundLogger), "info", test_dict)
                if "service" in result:
                    assert result["service"] == "custom-service"
                    break

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_json_output_for_docker(self, mock_utils, test_config):
        """Should use JSON output for Docker environment."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "docker"

        _, use_json = _configure_processors(
            test_config, is_docker=True, has_systemd=False, is_development=False
        )

        assert use_json is True

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch.dict(os.environ, {"BIRDNETPI_JSON_LOGS": "true"})
    def test_development_json_override(self, mock_utils, test_config):
        """Should allow JSON override in development."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "development"

        _, use_json = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=True
        )

        assert use_json is True

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_adds_location_when_available(self, mock_utils, test_config):
        """Should add location field when coordinates are non-zero."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"

        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Find and test the static context processor
        for processor in processors:
            if hasattr(processor, "__name__") and "processor" in processor.__name__:
                test_dict = {}
                result = processor(Mock(spec=structlog.BoundLogger), "info", test_dict)
                if "location" in result:
                    assert result["location"] == "45.5,-73.6"
                    break

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_no_location_when_zero(self, mock_utils, test_config):
        """Should not add location field when coordinates are 0,0."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"
        test_config.latitude = 0.0
        test_config.longitude = 0.0

        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Find and test the static context processor
        for processor in processors:
            if hasattr(processor, "__name__") and "processor" in processor.__name__:
                test_dict = {}
                result = processor(Mock(spec=structlog.BoundLogger), "info", test_dict)
                assert "location" not in result
                break

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_handles_missing_site_name(self, mock_utils, test_config):
        """Should handle missing site_name attribute gracefully."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"
        # Remove site_name attribute
        delattr(test_config, "site_name")

        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Find and test the static context processor
        for processor in processors:
            if hasattr(processor, "__name__") and "processor" in processor.__name__:
                test_dict = {}
                result = processor(Mock(spec=structlog.BoundLogger), "info", test_dict)
                # Should not have site_name field
                assert "site_name" not in result
                break

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    def test_handles_empty_site_name(self, mock_utils, test_config):
        """Should not include site_name field when it's empty."""
        mock_utils.get_git_version.return_value = "v1.0.0"
        mock_utils.get_deployment_environment.return_value = "production"
        test_config.site_name = ""

        processors, _ = _configure_processors(
            test_config, is_docker=False, has_systemd=False, is_development=False
        )

        # Find and test the static context processor
        for processor in processors:
            if hasattr(processor, "__name__") and "processor" in processor.__name__:
                test_dict = {}
                result = processor(Mock(spec=structlog.BoundLogger), "info", test_dict)
                # Should not have site_name field when empty
                assert "site_name" not in result
                break


class TestConfigureHandlers:
    """Test handler configuration."""

    @pytest.fixture
    def test_config(self):
        """Should create a mock BirdNET config."""
        config = MagicMock(spec=BirdNETConfig)
        config.logging = LoggingConfig(
            level="info",
            json_logs=True,
            include_caller=False,
            extra_fields={},
        )
        return config

    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    def test_clears_existing_handlers(self, mock_get_logger, test_config):
        """Should clear existing handlers before adding new ones."""
        mock_logger = Mock(spec=logging.Logger)
        mock_handler1 = Mock(spec=logging.Handler)
        mock_handler2 = Mock(spec=logging.Handler)
        mock_logger.handlers = [mock_handler1, mock_handler2]
        mock_get_logger.return_value = mock_logger

        _configure_handlers(test_config, use_json=True, has_systemd=False, is_development=False)

        # Should remove both handlers
        assert mock_logger.removeHandler.call_count == 2
        mock_logger.removeHandler.assert_any_call(mock_handler1)
        mock_logger.removeHandler.assert_any_call(mock_handler2)

    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.logging.StreamHandler", autospec=True)
    def test_adds_console_handler_for_non_systemd(
        self, mock_stream_handler, mock_get_logger, test_config
    ):
        """Should add console handler when systemd is not available."""
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []
        mock_get_logger.return_value = mock_logger
        mock_handler = Mock(spec=logging.Handler)
        mock_stream_handler.return_value = mock_handler

        _configure_handlers(test_config, use_json=False, has_systemd=False, is_development=False)

        # Should create stream handler for stdout
        mock_stream_handler.assert_called_once_with(sys.stdout)
        # Should add handler to logger
        mock_logger.addHandler.assert_called_once_with(mock_handler)
        # Should set formatter
        assert mock_handler.setFormatter.called

    @patch("birdnetpi.system.structlog_configurator._add_journald_handler", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    def test_uses_journald_for_systemd(self, mock_get_logger, mock_add_journald, test_config):
        """Should use journald handler when systemd is available."""
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []
        mock_get_logger.return_value = mock_logger

        _configure_handlers(test_config, use_json=True, has_systemd=True, is_development=False)

        # Should call journald handler setup
        mock_add_journald.assert_called_once()
        assert test_config in mock_add_journald.call_args[0]

    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.logging.StreamHandler", autospec=True)
    def test_development_uses_console(self, mock_stream_handler, mock_get_logger, test_config):
        """Should use console handler in development even with systemd."""
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []
        mock_get_logger.return_value = mock_logger
        mock_handler = Mock(spec=logging.Handler)
        mock_stream_handler.return_value = mock_handler

        _configure_handlers(test_config, use_json=False, has_systemd=True, is_development=True)

        # Should use console handler, not journald
        mock_stream_handler.assert_called_once_with(sys.stdout)
        mock_logger.addHandler.assert_called_once_with(mock_handler)


class TestJournaldHandler:
    """Test journald handler configuration."""

    @patch("birdnetpi.system.structlog_configurator.sys.stderr", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.logging.StreamHandler", autospec=True)
    def test_fallback_when_systemd_not_available(self, mock_stream_handler, mock_stderr):
        """Should fallback to stderr when systemd module is not available."""
        test_config = Mock(spec=LoggingConfig)
        mock_logger = Mock(spec=logging.Logger)
        mock_formatter = Mock(spec=logging.Formatter)
        mock_handler = Mock(spec=logging.Handler)
        mock_stream_handler.return_value = mock_handler

        # Simulate ImportError for systemd module
        with patch.dict("sys.modules", {"systemd": None, "systemd.journal": None}):
            _add_journald_handler(test_config, mock_logger, logging.INFO, mock_formatter)

        # Should create stderr handler as fallback
        mock_stream_handler.assert_called_once_with(mock_stderr)
        mock_logger.addHandler.assert_called_once_with(mock_handler)
        mock_handler.setFormatter.assert_called_once_with(mock_formatter)


class TestConfigureStructlog:
    """Test the main configuration function."""

    @pytest.fixture
    def test_config(self):
        """Should create a mock BirdNET config."""
        config = MagicMock(spec=BirdNETConfig)
        config.logging = LoggingConfig(
            level="info",
            json_logs=None,
            include_caller=False,
            extra_fields={"custom": "field"},
        )
        config.site_name = "Test Site"
        return config

    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    @patch("birdnetpi.system.structlog_configurator._configure_handlers", autospec=True)
    @patch("birdnetpi.system.structlog_configurator._configure_processors", autospec=True)
    @patch("birdnetpi.system.structlog_configurator._get_environment_config", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.structlog.configure", autospec=True)
    def test_full_configuration(
        self,
        mock_structlog_configure,
        mock_get_env,
        test_configure_processors,
        test_configure_handlers,
        mock_get_logger,
        test_config,
    ):
        """Should perform full structlog configuration."""
        # Setup mocks
        mock_get_env.return_value = (False, False, False)  # Not Docker, no systemd, not dev
        mock_processors = [Mock(spec=callable), Mock(spec=callable)]
        test_configure_processors.return_value = (mock_processors, False)
        mock_logger = Mock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger

        # Run configuration
        configure_structlog(test_config)

        # Verify calls
        mock_get_env.assert_called_once()
        test_configure_processors.assert_called_once_with(test_config, False, False, False)
        mock_structlog_configure.assert_called_once()
        test_configure_handlers.assert_called_once_with(test_config, False, False, False)

        # Verify logging of success
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Structured logging configured" in call_args[0]
        assert "extra" in call_args[1]

    @patch("birdnetpi.system.structlog_configurator.SystemUtils", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.structlog.configure", autospec=True)
    def test_logging_success_message(
        self, mock_structlog_configure, mock_get_logger, mock_utils, test_config
    ):
        """Should log configuration success with appropriate metadata."""
        mock_utils.is_docker_environment.return_value = False
        mock_utils.is_systemd_available.return_value = True
        mock_utils.get_git_version.return_value = "v1.2.3"
        mock_utils.get_deployment_environment.return_value = "production"

        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []  # Add empty handlers list
        mock_get_logger.return_value = mock_logger

        configure_structlog(test_config)

        # Check success log
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        extra = call_args[1]["extra"]
        assert extra["git_version"] == "v1.2.3"
        assert extra["log_level"] == "info"
        assert extra["environment"] == "production"
        assert extra["journald"] is True
        assert extra["json_output"] is None  # From test_config

    @patch("birdnetpi.system.structlog_configurator.logging.getLogger", autospec=True)
    @patch("birdnetpi.system.structlog_configurator.structlog.configure", autospec=True)
    def test_configures_filtering_bound_logger(
        self, mock_structlog_configure, mock_get_logger, test_config
    ):
        """Should configure filtering bound logger with correct log level."""
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []  # Add empty handlers list
        mock_get_logger.return_value = mock_logger

        configure_structlog(test_config)

        # Get the configure call
        call_kwargs = mock_structlog_configure.call_args[1]

        # Check wrapper_class is a filtering bound logger
        assert "wrapper_class" in call_kwargs
        # Verify it's configured with the right log level (INFO = 20)
        # The actual wrapper class is created by structlog.make_filtering_bound_logger
