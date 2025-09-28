"""Test v2.0.0 git settings migration."""

import pytest

from birdnetpi.config.versions.v2_0_0 import ConfigVersion_2_0_0


class TestGitSettingsMigration:
    """Test migration of git settings to updates section."""

    @pytest.fixture
    def handler(self):
        """Create v2.0.0 handler."""
        return ConfigVersion_2_0_0()

    def test_git_settings_in_defaults(self, handler):
        """Should have git settings in updates section in defaults."""
        defaults = handler.defaults

        # Should NOT have git settings at root
        assert "git_branch" not in defaults
        assert "git_remote" not in defaults

        # Should have updates section with git settings
        assert "updates" in defaults
        assert defaults["updates"]["git_branch"] == "main"
        assert defaults["updates"]["git_remote"] == "origin"
        assert defaults["updates"]["check_enabled"] is True
        assert defaults["updates"]["check_interval_hours"] == 6

    def test_migrate_git_from_root_to_updates(self, handler):
        """Should migrate git settings from root to updates section."""
        old_config = {
            "config_version": "1.9.0",
            "site_name": "Test",
            "git_branch": "develop",
            "git_remote": "upstream",
        }

        migrated = handler.upgrade_from_previous(old_config)

        # Should NOT have git settings at root
        assert "git_branch" not in migrated
        assert "git_remote" not in migrated

        # Should have them in updates section
        assert "updates" in migrated
        assert migrated["updates"]["git_branch"] == "develop"
        assert migrated["updates"]["git_remote"] == "upstream"

    def test_preserve_existing_updates_section(self, handler):
        """Should preserve existing updates section when migrating."""
        old_config = {
            "config_version": "1.9.0",
            "site_name": "Test",
            "git_branch": "feature",
            "git_remote": "fork",
            "updates": {
                "check_enabled": False,
                "show_banner": False,
            },
        }

        migrated = handler.upgrade_from_previous(old_config)

        # Should preserve existing settings
        assert migrated["updates"]["check_enabled"] is False
        assert migrated["updates"]["show_banner"] is False

        # Should add git settings
        assert migrated["updates"]["git_branch"] == "feature"
        assert migrated["updates"]["git_remote"] == "fork"

        # Should add missing defaults
        assert migrated["updates"]["check_interval_hours"] == 6
        assert migrated["updates"]["auto_check_on_startup"] is True

    def test_no_git_settings_uses_defaults(self, handler):
        """Should use default git settings if not present."""
        old_config = {
            "config_version": "1.9.0",
            "site_name": "Test",
        }

        migrated = handler.upgrade_from_previous(old_config)

        # Should have default git settings in updates
        assert migrated["updates"]["git_branch"] == "main"
        assert migrated["updates"]["git_remote"] == "origin"

    def test_apply_defaults_with_updates(self, handler):
        """Should apply defaults correctly with updates section."""
        config = {
            "site_name": "My Site",
            "updates": {
                "git_branch": "custom",
            },
        }

        with_defaults = handler.apply_defaults(config)

        # Should have the custom git_branch
        assert with_defaults["updates"]["git_branch"] == "custom"

        # Should have default git_remote
        assert with_defaults["updates"]["git_remote"] == "origin"

        # Should have other update defaults
        assert with_defaults["updates"]["check_enabled"] is True
