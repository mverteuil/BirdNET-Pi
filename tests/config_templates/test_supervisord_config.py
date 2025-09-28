"""Test supervisord configuration template."""

import configparser

import pytest


@pytest.fixture
def supervisord_config(repo_root):
    """Load supervisord configuration."""
    config_path = repo_root / "config_templates" / "supervisord.conf"
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


class TestSupervisordConfig:
    """Test supervisord configuration for update daemon."""

    def test_update_migrate_program_exists(self, supervisord_config):
        """Should have update_migrate program configured."""
        assert "program:update_migrate" in supervisord_config
        section = supervisord_config["program:update_migrate"]

        # Check critical settings
        assert section["command"] == "/opt/birdnetpi/.venv/bin/update-daemon --mode migrate"
        assert section["autostart"] == "true"
        assert section["autorestart"].startswith("false")  # One-shot
        assert section["priority"] == "1"  # First to run
        assert section["startsecs"] == "0"
        assert section["exitcodes"].startswith("0")

    def test_update_monitor_program_exists(self, supervisord_config):
        """Should have update_monitor program configured."""
        assert "program:update_monitor" in supervisord_config
        section = supervisord_config["program:update_monitor"]

        # Check critical settings
        assert section["command"] == "/opt/birdnetpi/.venv/bin/update-daemon --mode monitor"
        assert section["autostart"] == "true"
        assert section["autorestart"] == "true"  # Continuous
        assert section["priority"] == "400"  # After other services

    def test_priority_ordering(self, supervisord_config):
        """Should have correct priority ordering for startup sequence."""
        priorities = {}
        for section in supervisord_config.sections():
            if section.startswith("program:"):
                program = section.replace("program:", "")
                if "priority" in supervisord_config[section]:
                    priorities[program] = int(supervisord_config[section]["priority"])

        # Verify ordering
        assert priorities.get("update_migrate") == 1  # First
        assert priorities.get("redis") == 50  # Infrastructure
        assert priorities.get("pulseaudio") == 100  # Audio system
        assert priorities.get("audio_capture") == 200  # Audio services
        assert priorities.get("audio_analysis") == 300
        assert priorities.get("audio_websocket") == 300
        assert priorities.get("update_monitor") == 400  # Last

    def test_all_programs_have_logging(self, supervisord_config):
        """Should have proper logging configuration for all programs."""
        for section in supervisord_config.sections():
            if section.startswith("program:"):
                assert "stdout_logfile" in supervisord_config[section]
                assert "stderr_logfile" in supervisord_config[section]
                # Docker logging to stdout/stderr
                assert supervisord_config[section]["stdout_logfile"] in ["/dev/fd/1", "/dev/stdout"]
                assert supervisord_config[section]["stderr_logfile"] in ["/dev/fd/2", "/dev/stderr"]

    def test_update_programs_have_environment(self, supervisord_config):
        """Should have proper environment for update programs."""
        for program in ["update_migrate", "update_monitor"]:
            section = f"program:{program}"
            assert "environment" in supervisord_config[section]
            env = supervisord_config[section]["environment"]
            assert "PYTHONPATH=/opt/birdnetpi/src" in env
            assert f"SERVICE_NAME={program}" in env

    def test_redis_starts_before_monitors(self, supervisord_config):
        """Should ensure Redis starts before update monitor."""
        redis_priority = int(supervisord_config["program:redis"]["priority"])
        monitor_priority = int(supervisord_config["program:update_monitor"]["priority"])

        assert redis_priority < monitor_priority, "Redis must start before update monitor"
