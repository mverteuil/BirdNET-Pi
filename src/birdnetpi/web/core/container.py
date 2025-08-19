"""Dependency injection container for the BirdNET-Pi application."""

from dependency_injector import containers, providers
from fastapi.templating import Jinja2Templates

from birdnetpi.analytics.data_preparation_manager import DataPreparationManager
from birdnetpi.analytics.plotting_manager import PlottingManager
from birdnetpi.analytics.reporting_manager import ReportingManager
from birdnetpi.audio.audio_websocket_service import AudioWebSocketService
from birdnetpi.audio.spectrogram_service import SpectrogramService
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.database.ioc.database_service import IOCDatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import DetectionQueryService
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.location.gps_service import GPSService
from birdnetpi.location.location_service import LocationService
from birdnetpi.notifications.mqtt import MQTTService
from birdnetpi.notifications.notification_manager import NotificationManager
from birdnetpi.notifications.webhooks import WebhookService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control_service import SystemControlService
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.config import get_config


def create_jinja2_templates(resolver: PathResolver) -> Jinja2Templates:
    """Create Jinja2Templates with dynamic path from resolver."""
    return Jinja2Templates(directory=str(resolver.get_templates_dir()))


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

    bnp_database_service = providers.Singleton(
        DatabaseService,
        db_path=database_path,
    )

    # IOC database service
    ioc_database_service = providers.Singleton(
        IOCDatabaseService,
        db_path=providers.Factory(
            lambda resolver: resolver.get_ioc_database_path(), resolver=path_resolver
        ),
    )

    # Multilingual database service with all three bird name databases
    multilingual_database_service = providers.Singleton(
        MultilingualDatabaseService,
        path_resolver=path_resolver,
    )

    # Detection query service - now uses multilingual service
    detection_query_service = providers.Factory(
        DetectionQueryService,
        bnp_database_service=bnp_database_service,
        multilingual_service=multilingual_database_service,
    )

    # Cache service - singleton for analytics performance
    cache_service = providers.Singleton(
        Cache,
        # Use default settings optimized for SBC deployments
        memcached_host="localhost",
        memcached_port=11211,
        default_ttl=300,
        enable_cache_warming=True,
    )

    # Core business services - singletons
    file_manager = providers.Singleton(
        FileManager,
        path_resolver=path_resolver,
    )

    # Species display service - singleton
    species_display_service = providers.Singleton(
        SpeciesDisplayService,
        config=config,
    )

    # Data Manager - single source of truth for detection data access and event emission
    data_manager = providers.Singleton(
        DataManager,
        database_service=bnp_database_service,
        multilingual_service=multilingual_database_service,
        species_display_service=species_display_service,
        detection_query_service=detection_query_service,
    )

    location_service = providers.Singleton(
        LocationService,
        latitude=providers.Factory(lambda c: c.latitude, c=config),
        longitude=providers.Factory(lambda c: c.longitude, c=config),
    )

    # Data analysis services - singletons
    data_preparation_manager = providers.Singleton(
        DataPreparationManager,
        config=config,
        location_service=location_service,
    )

    plotting_manager = providers.Singleton(
        PlottingManager,
        data_preparation_manager=data_preparation_manager,
    )

    # System services - singletons
    system_control_service = providers.Singleton(SystemControlService)

    # Audio services - singletons
    audio_websocket_service = providers.Singleton(
        AudioWebSocketService,
        path_resolver=path_resolver,
    )

    spectrogram_service = providers.Singleton(
        SpectrogramService,
        sample_rate=providers.Factory(lambda c: c.sample_rate, c=config),
        channels=providers.Factory(lambda c: c.audio_channels, c=config),
        window_size=1024,  # Good balance of frequency/time resolution
        overlap=0.75,  # High overlap for smooth visualization
        update_rate=15.0,  # 15 FPS for smooth real-time display
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

    # Notification manager - singleton (depends on other services)
    notification_manager = providers.Singleton(
        NotificationManager,
        active_websockets=providers.Object(set()),  # Will be set by factory
        config=config,
        mqtt_service=mqtt_service,
        webhook_service=webhook_service,
    )

    # Request-scoped managers (factories - new instance per request)
    reporting_manager = providers.Factory(
        ReportingManager,
        data_manager=data_manager,
        path_resolver=path_resolver,
        config=config,
        plotting_manager=plotting_manager,
        data_preparation_manager=data_preparation_manager,
        location_service=location_service,
        species_display_service=species_display_service,
    )
