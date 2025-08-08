"""Dependency injection container for the BirdNET-Pi application."""

from pathlib import Path

from dependency_injector import containers, providers
from fastapi.templating import Jinja2Templates

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.file_manager import FileManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.services.audio_websocket_service import AudioWebSocketService
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_query_service import DetectionQueryService
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.ioc_database_service import IOCDatabaseService
from birdnetpi.services.location_service import LocationService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.services.spectrogram_service import SpectrogramService
from birdnetpi.services.system_control_service import SystemControlService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.core.config import get_config


class Container(containers.DeclarativeContainer):
    """Application dependency injection container.

    This container defines all services and their dependencies,
    replacing the manual instantiation that was previously done in main.py.
    Services are configured as singletons or factories based on their usage patterns.
    """

    # Configuration - singleton instance cached by @lru_cache
    config = providers.Singleton(get_config)

    # Core infrastructure services - singletons
    file_resolver = providers.Singleton(FilePathResolver)

    # Templates configuration - singleton
    templates = providers.Singleton(
        Jinja2Templates,
        directory=str(Path(__file__).parent.parent / "templates"),
    )

    # Database path provider
    database_path = providers.Factory(
        lambda resolver: resolver.get_database_path(),
        resolver=file_resolver,
    )

    bnp_database_service = providers.Singleton(
        DatabaseService,
        db_path=database_path,
    )

    # IOC database service factory with error handling
    def _create_ioc_service(resolver):
        """Create IOC database service with graceful error handling."""
        try:
            return IOCDatabaseService(resolver.get_ioc_database_path())
        except Exception as e:
            print(f"Warning: IOC database service unavailable: {e}")
            return None

    ioc_database_service = providers.Singleton(
        _create_ioc_service,
        resolver=file_resolver,
    )

    # Detection query service factory with error handling
    def _create_detection_query_service(bnp_service, ioc_service):
        """Create detection query service with graceful error handling."""
        try:
            if ioc_service is None:
                return None
            return DetectionQueryService(bnp_service, ioc_service)
        except Exception as e:
            print(f"Warning: Detection query service unavailable: {e}")
            return None

    detection_query_service = providers.Factory(
        _create_detection_query_service,
        bnp_service=bnp_database_service,
        ioc_service=ioc_database_service,
    )

    # Core business services - singletons
    file_manager = providers.Singleton(
        FileManager,
        base_dir=file_resolver.provided.base_dir,
    )

    detection_manager = providers.Singleton(
        DetectionManager,
        bnp_database_service=bnp_database_service,
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

    # Hardware monitoring service - singleton
    hardware_monitor_service = providers.Singleton(
        HardwareMonitorService,
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

    # Notification service - singleton (depends on other services)
    notification_service = providers.Singleton(
        NotificationService,
        active_websockets=providers.Object(set()),  # Will be set by factory
        config=config,
        mqtt_service=mqtt_service,
        webhook_service=webhook_service,
    )

    # Request-scoped managers (factories - new instance per request)
    reporting_manager = providers.Factory(
        ReportingManager,
        detection_manager=detection_manager,
        file_path_resolver=file_resolver,
        config=config,
        plotting_manager=plotting_manager,
        data_preparation_manager=data_preparation_manager,
        location_service=location_service,
    )
