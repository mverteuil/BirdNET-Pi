"""Integration tests for development warning banner functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from jinja2 import Environment, FileSystemLoader

from birdnetpi.config.models import BirdNETConfig, UpdateConfig
from birdnetpi.daemons.update_daemon import DaemonState, process_update_request
from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.middleware.update_banner import add_update_status_to_templates


class TestDevelopmentWarningBanner:
    """Test the development warning banner display logic."""

    @pytest.fixture
    def mock_config_with_dev_warning(self):
        """Create config with development warning enabled."""
        config = MagicMock(spec=BirdNETConfig)
        config.updates = MagicMock(spec=UpdateConfig)
        config.updates.show_development_warning = True
        config.updates.show_banner = True
        return config

    @pytest.fixture
    def mock_config_no_dev_warning(self):
        """Create config with development warning disabled."""
        config = MagicMock(spec=BirdNETConfig)
        config.updates = MagicMock(spec=UpdateConfig)
        config.updates.show_development_warning = False
        config.updates.show_banner = True
        return config

    def test_development_warning_shows_when_enabled(self, cache):
        """Should show development warning when on dev version and enabled."""
        # Create mock container with configured services
        container = Container()
        mock_config = MagicMock(spec=BirdNETConfig)
        mock_config.updates = MagicMock(spec=UpdateConfig)
        mock_config.updates.show_development_warning = True
        mock_config.updates.show_banner = True

        # Override container providers
        with container.cache_service.override(cache):
            with container.config.override(mock_config):
                # Set cache to indicate development version
                cache.get.return_value = {
                    "current_version": "dev-abc1234",
                    "latest_version": "v1.0.0",
                    "version_type": "development",
                    "available": False,
                }

                # Create a test environment
                templates = Environment()

                # Add the update status functions
                add_update_status_to_templates(templates, container)

                # Test the show_development_warning function
                show_dev_warning = templates.globals["show_development_warning"]
                assert callable(show_dev_warning)
                assert show_dev_warning() is True

    def test_development_warning_hidden_when_disabled(self, cache):
        """Should not show development warning when disabled in config."""
        # Create mock container with configured services
        container = Container()
        mock_config = MagicMock(spec=BirdNETConfig)
        mock_config.updates = MagicMock(spec=UpdateConfig)
        mock_config.updates.show_development_warning = False
        mock_config.updates.show_banner = True

        # Override container providers
        with container.cache_service.override(cache):
            with container.config.override(mock_config):
                # Set cache to indicate development version
                cache.get.return_value = {
                    "current_version": "dev-abc1234",
                    "latest_version": "v1.0.0",
                    "version_type": "development",
                    "available": False,
                }

                # Create a test environment
                templates = Environment()

                # Add the update status functions
                add_update_status_to_templates(templates, container)

                # Test the show_development_warning function
                show_dev_warning = templates.globals["show_development_warning"]
                assert show_dev_warning() is False

    def test_development_warning_hidden_on_release(self, cache):
        """Should not show development warning when on a release version."""
        # Create mock container with configured services
        container = Container()
        mock_config = MagicMock(spec=BirdNETConfig)
        mock_config.updates = MagicMock(spec=UpdateConfig)
        mock_config.updates.show_development_warning = True
        mock_config.updates.show_banner = True

        # Override container providers
        with container.cache_service.override(cache):
            with container.config.override(mock_config):
                # Set cache to indicate release version
                cache.get.return_value = {
                    "current_version": "v1.0.0",
                    "latest_version": "v1.1.0",
                    "version_type": "release",
                    "available": True,
                }

                # Create a test environment
                templates = Environment()

                # Add the update status functions
                add_update_status_to_templates(templates, container)

                # Test the show_development_warning function
                show_dev_warning = templates.globals["show_development_warning"]
                assert show_dev_warning() is False

    def test_template_renders_development_banner(self, repo_root):
        """Should render development banner correctly in template."""
        # Create a test environment with our templates
        template_dir = repo_root / "src/birdnetpi/web/templates"
        env = Environment(
            loader=FileSystemLoader(
                [template_dir, template_dir / "includes", template_dir / "components"]
            )
        )

        # Mock the template functions
        def mock_get_update_status():
            return {
                "current_version": "dev-main123",
                "latest_version": "v1.0.0",
                "version_type": "development",
                "available": False,
            }

        def mock_show_development_warning():
            status = mock_get_update_status()
            return status and status.get("version_type") == "development"

        def mock_translation(text):
            return text  # Simple passthrough for testing

        def mock_url_for(name):
            return f"/{name}"  # Simple URL generation for testing

        env.globals["get_update_status"] = mock_get_update_status
        env.globals["show_development_warning"] = mock_show_development_warning
        env.globals["_"] = mock_translation
        env.globals["url_for"] = mock_url_for
        env.globals["update_status"] = mock_get_update_status()

        # Load and render the update banner template
        template = env.get_template("update_banner.html.j2")
        rendered = template.render()

        # Check that development banner is present
        assert "development-banner" in rendered
        assert "Development Version" in rendered
        assert "dev-main123" in rendered
        assert "This is not a stable release" in rendered

        # Check that update banner is NOT present (no update available)
        assert 'id="update-banner"' not in rendered

    def test_template_renders_update_banner(self, repo_root):
        """Should render update banner when update is available."""
        # Create a test environment with our templates
        template_dir = repo_root / "src/birdnetpi/web/templates"
        env = Environment(
            loader=FileSystemLoader(
                [template_dir, template_dir / "includes", template_dir / "components"]
            )
        )

        # Mock the template functions
        def mock_get_update_status():
            return {
                "current_version": "v0.9.0",
                "latest_version": "v1.0.0",
                "version_type": "release",
                "available": True,
                "release_notes": "Major new features!\nBug fixes",
            }

        def mock_show_development_warning():
            return False  # Not a development version

        def mock_translation(text):
            return text  # Simple passthrough for testing

        def mock_url_for(name):
            return f"/{name}"  # Simple URL generation for testing

        env.globals["get_update_status"] = mock_get_update_status
        env.globals["show_development_warning"] = mock_show_development_warning
        env.globals["_"] = mock_translation
        env.globals["url_for"] = mock_url_for
        env.globals["update_status"] = mock_get_update_status()

        # Load and render the update banner template
        template = env.get_template("update_banner.html.j2")
        rendered = template.render()

        # Check that update banner is present
        assert 'id="update-banner"' in rendered
        assert "A new version is available!" in rendered
        assert "v1.0.0" in rendered
        assert "Major new features!" in rendered

        # Check that development banner element is NOT present
        assert 'id="development-banner"' not in rendered

    def test_both_banners_can_show(self, repo_root):
        """Should show both banners when on dev version AND update available."""
        # Create a test environment with our templates
        template_dir = repo_root / "src/birdnetpi/web/templates"
        env = Environment(
            loader=FileSystemLoader(
                [template_dir, template_dir / "includes", template_dir / "components"]
            )
        )

        # Mock the template functions
        def mock_get_update_status():
            return {
                "current_version": "dev-abc123",
                "latest_version": "v1.0.0",
                "version_type": "development",
                "available": True,  # Update is available
                "release_notes": "Latest stable release",
            }

        def mock_show_development_warning():
            status = mock_get_update_status()
            return status and status.get("version_type") == "development"

        def mock_translation(text):
            return text  # Simple passthrough for testing

        def mock_url_for(name):
            return f"/{name}"  # Simple URL generation for testing

        env.globals["get_update_status"] = mock_get_update_status
        env.globals["show_development_warning"] = mock_show_development_warning
        env.globals["_"] = mock_translation
        env.globals["url_for"] = mock_url_for
        env.globals["update_status"] = mock_get_update_status()

        # Load and render the update banner template
        template = env.get_template("update_banner.html.j2")
        rendered = template.render()

        # Check that BOTH banners are present
        assert "development-banner" in rendered
        assert "Development Version" in rendered
        assert 'id="update-banner"' in rendered
        assert "A new version is available!" in rendered


class TestUpdateDaemonIntegration:
    """Update daemon properly sets version_type."""

    @pytest.mark.asyncio
    async def test_daemon_sets_version_type_on_check(self, path_resolver, cache):
        """Should set version_type when daemon performs update check."""
        # Set up daemon state
        DaemonState.cache_service = cache
        DaemonState.update_manager = MagicMock(spec=UpdateManager)

        # Mock the check to return development version
        mock_status = {
            "current_version": "dev-main456",
            "latest_version": "v2.0.0",
            "version_type": "development",
            "available": True,
            "checked_at": "2024-01-01T12:00:00",
        }
        DaemonState.update_manager.check_for_updates = AsyncMock(
            spec=callable, return_value=mock_status
        )

        # Process a check request
        await process_update_request({"action": "check"})

        # Verify cache was updated with version_type
        cache.set.assert_called()
        call_args = cache.set.call_args_list

        # Find the call that sets update:status
        status_call = None
        for call in call_args:
            if call[0][0] == "update:status":
                status_call = call
                break

        assert status_call is not None
        cached_status = status_call[0][1]
        assert cached_status["version_type"] == "development"
