"""Integration tests for the Container with real dependency injection."""

import shutil
from pathlib import Path

import pytest
from dependency_injector import providers

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container


class TestContainerIntegration:
    """Test that the Container can be properly instantiated with test paths."""

    @pytest.fixture
    def test_paths(self, tmp_path: Path, repo_root: Path):
        """Should create test directory structure with real assets copied."""
        # Create directory structure
        (tmp_path / "database").mkdir(parents=True)
        (tmp_path / "config").mkdir(parents=True)

        # Copy real IOC database to temp location
        real_ioc_db = repo_root / "data" / "database" / "ioc_reference.db"
        if real_ioc_db.exists():
            temp_ioc_db = tmp_path / "database" / "ioc_reference.db"
            shutil.copy(real_ioc_db, temp_ioc_db)

        # Copy real multilingual databases
        for db_name in ["avibase_database.db", "patlevin_database.db"]:
            real_db = repo_root / "data" / "database" / db_name
            if real_db.exists():
                temp_db = tmp_path / "database" / db_name
                shutil.copy(real_db, temp_db)

        # Copy config template
        real_config = repo_root / "config_templates" / "birdnetpi.yaml"
        if real_config.exists():
            temp_config = tmp_path / "config" / "birdnetpi.yaml"
            shutil.copy(real_config, temp_config)

        return tmp_path

    @pytest.fixture
    def test_resolver(self, test_paths: Path, repo_root: Path):
        """Should create a PathResolver configured for testing."""
        resolver = PathResolver()

        # Override writable paths to use temp directory
        resolver.get_database_path = lambda: test_paths / "database" / "birdnetpi.db"
        resolver.get_birdnetpi_config_path = lambda: test_paths / "config" / "birdnetpi.yaml"

        # Override read-only database paths to use temp copies
        resolver.get_ioc_database_path = lambda: test_paths / "database" / "ioc_reference.db"
        resolver.get_avibase_database_path = lambda: test_paths / "database" / "avibase_database.db"
        resolver.get_patlevin_database_path = (
            lambda: test_paths / "database" / "patlevin_database.db"
        )

        # Keep real paths for models, static files, templates
        resolver.get_models_dir = lambda: repo_root / "data" / "models"
        resolver.get_static_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "static"
        resolver.get_templates_dir = lambda: repo_root / "src" / "birdnetpi" / "web" / "templates"
        resolver.get_config_template_path = (
            lambda: repo_root / "config_templates" / "birdnetpi.yaml"
        )

        return resolver

    @pytest.fixture
    def container_with_overrides(self, test_resolver: PathResolver):
        """Create a Container with test path overrides."""
        import gc
        import time

        container = Container()

        # Override path_resolver
        container.path_resolver.override(providers.Singleton(lambda: test_resolver))

        # Override database_path factory
        container.database_path.override(
            providers.Factory(lambda: test_resolver.get_database_path())
        )

        yield container

        # Clean up singleton instances to prevent resource leaks
        # Reset all singleton providers to ensure clean state
        if container.core_database.provided:
            container.core_database.reset()
        if container.species_database.provided:
            container.species_database.reset()
        if container.cache_service.provided:
            container.cache_service.reset()

        # Clean up overrides
        container.path_resolver.reset_override()
        container.database_path.reset_override()

        # Force garbage collection to release SQLite locks
        gc.collect()
        # Small delay to ensure SQLite releases file locks
        time.sleep(0.01)

    def test_container_creation(self):
        """Should container can be created without errors."""
        container = Container()
        assert container is not None
        assert hasattr(container, "path_resolver")
        assert hasattr(container, "config")
        assert hasattr(container, "core_database")

    def test_container_wiring(self, container_with_overrides: Container):
        """Should container can be wired with all modules."""
        container_with_overrides.wire(
            modules=[
                "birdnetpi.web.core.factory",
                "birdnetpi.web.routers.settings_api_routes",
                "birdnetpi.web.routers.settings_view_routes",
                "birdnetpi.web.routers.detections_api_routes",
                "birdnetpi.web.routers.multimedia_view_routes",
                "birdnetpi.web.routers.sqladmin_view_routes",
                "birdnetpi.web.routers.system_api_routes",
                "birdnetpi.web.routers.websocket_routes",
            ]
        )
        # If no exception is raised, wiring succeeded

    def test_path_resolver_provider(
        self, container_with_overrides: Container, test_resolver: PathResolver
    ):
        """Should return the correct path_resolver instance from provider."""
        resolver = container_with_overrides.path_resolver()
        assert resolver is test_resolver
        assert resolver.get_database_path().parent.name == "database"

    def test_config_provider(self, container_with_overrides: Container):
        """Should config provider can be instantiated."""
        config = container_with_overrides.config()
        assert config is not None
        assert hasattr(config, "site_name")

    def test_database_service_provider(self, container_with_overrides: Container, test_paths: Path):
        """Should core_database provider uses test paths."""
        db_service = container_with_overrides.core_database()
        try:
            assert isinstance(db_service, CoreDatabaseService)
            assert str(test_paths) in str(db_service.db_path)
        finally:
            # Note: async_engine.dispose() is async and can't be called here
            # The container cleanup will handle it via reset_singleton()
            pass

    def test_species_database_provider(self, container_with_overrides: Container):
        """Should species_database can be instantiated."""
        species_database = container_with_overrides.species_database()
        assert species_database is not None

    def test_cache_service_provider(self, container_with_overrides: Container):
        """Should cache_service can be instantiated (falls back to in-memory)."""
        cache_service = container_with_overrides.cache_service()
        assert cache_service is not None

    def test_all_critical_providers(self, container_with_overrides: Container):
        """Should instantiate all critical providers successfully."""
        critical_providers = [
            "path_resolver",
            "config",
            "translation_manager",
            "templates",
            "core_database",
            "species_database",
            "detection_query_service",
            "file_manager",
            "species_display_service",
            "data_manager",
            "sun_service",
            "system_control_service",
            "audio_websocket_service",
            "gps_service",
            "mqtt_service",
            "webhook_service",
            "notification_manager",
        ]

        for provider_name in critical_providers:
            provider = getattr(container_with_overrides, provider_name)
            try:
                instance = provider()
                assert instance is not None, f"Provider {provider_name} returned None"
            except Exception as e:
                pytest.fail(f"Failed to instantiate {provider_name}: {e}")

    def test_provider_singleton_behavior(self, container_with_overrides: Container):
        """Should singleton providers return the same instance."""
        # Get two instances of a singleton provider
        db_service1 = container_with_overrides.core_database()
        db_service2 = container_with_overrides.core_database()

        # They should be the same instance
        assert db_service1 is db_service2

    def test_provider_factory_behavior(self, container_with_overrides: Container):
        """Should factory providers return new instances."""
        # detection_query_service is defined as a Factory
        service1 = container_with_overrides.detection_query_service()
        service2 = container_with_overrides.detection_query_service()

        # They should be different instances
        assert service1 is not service2

    def test_container_reset_overrides(self, test_resolver: PathResolver):
        """Should overrides can be properly reset."""
        container = Container()

        # Apply overrides
        container.path_resolver.override(providers.Singleton(lambda: test_resolver))
        resolver1 = container.path_resolver()
        assert resolver1 is test_resolver

        # Reset overrides
        container.path_resolver.reset_override()

        # Should get default resolver now
        resolver2 = container.path_resolver()
        assert resolver2 is not test_resolver
        assert isinstance(resolver2, PathResolver)
