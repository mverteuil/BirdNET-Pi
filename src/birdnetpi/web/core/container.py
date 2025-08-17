"""Dependency injection container for the BirdNET-Pi application."""

from dependency_injector import containers, providers
from fastapi.templating import Jinja2Templates

from birdnetpi.analytics.data_preparation_manager import DataPreparationManager
from birdnetpi.analytics.plotting_manager import PlottingManager
from birdnetpi.analytics.reporting_manager import ReportingManager
from birdnetpi.audio.audio_websocket_service import AudioWebSocketService
from birdnetpi.audio.spectrogram_service import SpectrogramService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.detection_query_service import DetectionQueryService
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.location.gps_service import GPSService
from birdnetpi.location.location_service import LocationService
from birdnetpi.managers.file_manager import FileManager
from birdnetpi.managers.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.notifications.mqtt_service import MQTTService
from birdnetpi.notifications.notification_manager import NotificationManager
from birdnetpi.notifications.webhook_service import WebhookService
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.ioc_database_service import IOCDatabaseService
from birdnetpi.services.species_display_service import SpeciesDisplayService
from birdnetpi.services.system_control_service import SystemControlService
from birdnetpi.utils.cache import Cache
from birdnetpi.utils.path_resolver import PathResolver
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

    # Configuration - singleton instance cached by @lru_cache
    config = providers.Singleton(get_config)

    # Core infrastructure services - singletons
    path_resolver = providers.Singleton(PathResolver)

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
        memcached_host=config.provided.cache_host
        if hasattr(config.provided, "cache_host")
        else "localhost",
        memcached_port=config.provided.cache_port
        if hasattr(config.provided, "cache_port")
        else 11211,
        default_ttl=config.provided.cache_ttl if hasattr(config.provided, "cache_ttl") else 300,
        enable_cache_warming=config.provided.enable_cache_warming
        if hasattr(config.provided, "enable_cache_warming")
        else True,
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
        latitude=config.provided.latitude,
        longitude=config.provided.longitude,
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
        samplerate=config.provided.sample_rate,
        channels=config.provided.audio_channels,
    )

    spectrogram_service = providers.Singleton(
        SpectrogramService,
        sample_rate=config.provided.sample_rate,
        channels=config.provided.audio_channels,
        window_size=1024,  # Good balance of frequency/time resolution
        overlap=0.75,  # High overlap for smooth visualization
        update_rate=15.0,  # 15 FPS for smooth real-time display
    )

    # GPS service - singleton
    gps_service = providers.Singleton(
        GPSService,
        enable_gps=config.provided.enable_gps,
        update_interval=config.provided.gps_update_interval,
    )

    # Hardware monitoring manager - singleton
    hardware_monitor_manager = providers.Singleton(
        HardwareMonitorManager,
        check_interval=config.provided.hardware_check_interval,
        audio_device_check=config.provided.enable_audio_device_check,
        system_resource_check=config.provided.enable_system_resource_check,
        gps_check=config.provided.enable_gps_check,
    )

    # IoT services - singletons
    mqtt_service = providers.Singleton(
        MQTTService,
        broker_host=config.provided.mqtt_broker_host,
        broker_port=config.provided.mqtt_broker_port,
        username=config.provided.mqtt_username,
        password=config.provided.mqtt_password,
        topic_prefix=config.provided.mqtt_topic_prefix,
        client_id=config.provided.mqtt_client_id,
        enable_mqtt=config.provided.enable_mqtt,
    )

    webhook_service = providers.Singleton(
        WebhookService,
        enable_webhooks=config.provided.enable_webhooks,
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
