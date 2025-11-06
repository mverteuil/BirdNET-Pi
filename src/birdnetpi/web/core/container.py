"""Dependency injection container for the BirdNET-Pi application."""

from dependency_injector import containers, providers
from fastapi.templating import Jinja2Templates
from jinja2 import StrictUndefined

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.audio.websocket import AudioWebSocketService
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.cleanup import DetectionCleanupService
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.location.gps import GPSService
from birdnetpi.location.sun import SunService
from birdnetpi.location.weather import WeatherSignalHandler
from birdnetpi.notifications.apprise import AppriseService
from birdnetpi.notifications.manager import NotificationManager
from birdnetpi.notifications.mqtt import MQTTService
from birdnetpi.notifications.webhooks import WebhookService
from birdnetpi.releases.registry_service import RegistryService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.log_reader import LogReaderService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.utils.auth import AuthService
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.config import get_config


def create_jinja2_templates(resolver: PathResolver) -> Jinja2Templates:
    """Create Jinja2Templates with dynamic path from resolver and strict undefined handling.

    Configures Jinja2 to raise errors on undefined variables (like Django),
    making missing template context painfully obvious during development.
    """
    templates = Jinja2Templates(directory=str(resolver.get_templates_dir()))

    # Enable strict mode - undefined variables raise errors instead of silently failing
    templates.env.undefined = StrictUndefined

    return templates


class Container(containers.DeclarativeContainer):
    """Application dependency injection container.

    This container defines all services and their dependencies,
    replacing the manual instantiation that was previously done in main.py.
    Services are configured as singletons or factories based on their usage patterns.
    """

    # Core infrastructure services - singletons
    path_resolver = providers.Singleton(PathResolver)

    # Configuration - singleton instance that uses our path_resolver
    config = providers.Singleton(
        get_config,
        path_resolver=path_resolver,
    )

    # Translation manager - singleton
    translation_manager = providers.Singleton(
        TranslationManager,
        path_resolver=path_resolver,
    )

    # Templates configuration - singleton
    templates = providers.Singleton(
        create_jinja2_templates,
        resolver=path_resolver,
    )

    # Database path provider
    database_path = providers.Factory(
        lambda resolver: resolver.get_database_path(),
        resolver=path_resolver,
    )

    core_database = providers.Singleton(
        CoreDatabaseService,
        db_path=database_path,
    )

    # Species database service with all three bird name databases
    species_database = providers.Singleton(
        SpeciesDatabaseService,
        path_resolver=path_resolver,
    )

    # eBird regional filtering service - singleton
    ebird_region_service = providers.Singleton(
        EBirdRegionService,
        path_resolver=path_resolver,
    )

    # eBird region pack registry service - singleton
    registry_service = providers.Singleton(
        RegistryService,
        path_resolver=path_resolver,
    )

    # Species display service - singleton
    species_display_service = providers.Singleton(
        SpeciesDisplayService,
        config=config,
    )

    # Detection query service
    detection_query_service = providers.Factory(
        DetectionQueryService,
        core_database=core_database,
        species_database=species_database,
        config=config,
    )

    # Cache service - singleton for analytics performance
    cache_service = providers.Singleton(
        Cache,
        # Use Redis for caching with memory-only mode
        redis_host="127.0.0.1",  # Use IP instead of localhost for Docker compatibility
        redis_port=6379,
        redis_db=0,
        default_ttl=300,
        enable_cache_warming=True,
    )

    # Authentication services
    auth_service = providers.Singleton(
        AuthService,
        path_resolver=path_resolver,
    )

    # Redis client for session storage - singleton
    redis_client = providers.Singleton(
        lambda: __import__("redis.asyncio", fromlist=["Redis"]).Redis.from_url(
            "redis://127.0.0.1:6379"
        ),
    )

    # Core business services - singletons
    file_manager = providers.Singleton(
        FileManager,
        path_resolver=path_resolver,
    )

    # Data Manager - single source of truth for detection data access and event emission
    data_manager = providers.Singleton(
        DataManager,
        database_service=core_database,
        species_database=species_database,
        species_display_service=species_display_service,
        file_manager=file_manager,
        path_resolver=path_resolver,
        detection_query_service=detection_query_service,
    )

    # Detection cleanup service for eBird filtering - singleton
    detection_cleanup_service = providers.Singleton(
        DetectionCleanupService,
        core_db=core_database,
        ebird_service=ebird_region_service,
        path_resolver=path_resolver,
        config=config,
    )

    sun_service = providers.Singleton(
        SunService,
        latitude=providers.Factory(lambda c: c.latitude, c=config),
        longitude=providers.Factory(lambda c: c.longitude, c=config),
    )

    # Weather signal handler - singleton
    weather_signal_handler = providers.Singleton(
        WeatherSignalHandler,
        database_service=core_database,
        latitude=providers.Factory(lambda c: c.latitude, c=config),
        longitude=providers.Factory(lambda c: c.longitude, c=config),
    )

    # System services - singletons
    system_control_service = providers.Singleton(SystemControlService)
    log_reader = providers.Singleton(LogReaderService)

    # Audio services - singletons
    audio_websocket_service = providers.Singleton(
        AudioWebSocketService,
        path_resolver=path_resolver,
    )

    # GPS service - singleton
    gps_service = providers.Singleton(
        GPSService,
        enable_gps=providers.Factory(lambda c: c.enable_gps, c=config),
        update_interval=providers.Factory(lambda c: c.gps_update_interval, c=config),
    )

    # Note: Hardware monitoring has been replaced with SystemInspector static methods
    # SystemInspector does not require dependency injection as it uses static methods

    # IoT services - singletons
    mqtt_service = providers.Singleton(
        MQTTService,
        broker_host=providers.Factory(lambda c: c.mqtt_broker_host, c=config),
        broker_port=providers.Factory(lambda c: c.mqtt_broker_port, c=config),
        username=providers.Factory(lambda c: c.mqtt_username, c=config),
        password=providers.Factory(lambda c: c.mqtt_password, c=config),
        topic_prefix=providers.Factory(lambda c: c.mqtt_topic_prefix, c=config),
        client_id=providers.Factory(lambda c: c.mqtt_client_id, c=config),
        enable_mqtt=providers.Factory(lambda c: c.enable_mqtt, c=config),
    )

    webhook_service = providers.Singleton(
        WebhookService,
        enable_webhooks=providers.Factory(lambda c: c.enable_webhooks, c=config),
    )

    apprise_service = providers.Singleton(
        AppriseService,
        enable_apprise=providers.Factory(
            lambda c: bool(c.apprise_targets or c.notification_rules),
            c=config,
        ),
    )

    # Notification manager - singleton (depends on other services)
    notification_manager = providers.Singleton(
        NotificationManager,
        active_websockets=providers.Object(set()),  # Will be set by factory
        config=config,
        core_database=core_database,
        species_db_service=species_database,
        detection_query_service=detection_query_service,
        mqtt_service=mqtt_service,
        webhook_service=webhook_service,
        apprise_service=apprise_service,
    )

    # Analytics and Presentation services
    analytics_manager = providers.Singleton(
        AnalyticsManager,
        detection_query_service=detection_query_service,
        config=config,
    )

    presentation_manager = providers.Singleton(
        PresentationManager,
        analytics_manager=analytics_manager,
        detection_query_service=detection_query_service,
        config=config,
        cache=cache_service,
    )
