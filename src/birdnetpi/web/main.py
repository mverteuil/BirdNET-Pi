import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqladmin import Admin, ModelView

from birdnetpi.managers.data_preparation_manager import DataPreparationManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.file_manager import FileManager
from birdnetpi.managers.plotting_manager import PlottingManager
from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.audio_fifo_reader_service import AudioFifoReaderService
from birdnetpi.services.audio_websocket_service import AudioWebSocketService
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.location_service import LocationService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.services.spectrogram_service import SpectrogramService
from birdnetpi.services.system_control_service import SystemControlService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.utils.logging_configurator import configure_logging

from .routers import (
    admin_router,
    audio_router,
    detections_router,
    field_mode_router,
    iot_router,
    overview_router,
    reporting_router,
    spectrogram_router,
    websocket_router,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager for application startup and shutdown events."""
    # Load configuration
    app.state.file_resolver = FilePathResolver()
    config_parser = ConfigFileParser()  # Uses env vars and FilePathResolver internally
    app.state.config = config_parser.load_config()
    app.mount(
        "/static",
        StaticFiles(directory=app.state.file_resolver.get_static_dir()),
        name="static",
    )

    # Initialize Jinja2Templates and store it in app.state
    app.state.templates = Jinja2Templates(directory=app.state.file_resolver.get_templates_dir())

    # Configure logging based on loaded config
    configure_logging(app.state.config)  # Added logging configuration

    # Initialize core services and managers
    app.state.db_service = DatabaseService(app.state.file_resolver.get_database_path())
    app.state.file_manager = FileManager(app.state.file_resolver.base_dir)
    app.state.detections = DetectionManager(app.state.db_service)
    app.state.location_service = LocationService(
        app.state.config.latitude, app.state.config.longitude
    )
    app.state.data_preparation_manager = DataPreparationManager(
        app.state.config, app.state.location_service
    )
    app.state.plotting_manager = PlottingManager(app.state.data_preparation_manager)
    app.state.service_manager = SystemControlService()
    app.state.active_websockets = set()  # Initialize set for active WebSocket connections
    app.state.audio_websocket_service = AudioWebSocketService(
        samplerate=app.state.config.sample_rate, channels=app.state.config.audio_channels
    )
    app.state.spectrogram_service = SpectrogramService(
        sample_rate=app.state.config.sample_rate,
        channels=app.state.config.audio_channels,
        window_size=1024,  # Good balance of frequency/time resolution
        overlap=0.75,  # High overlap for smooth visualization
        update_rate=15.0,  # 15 FPS for smooth real-time display
    )

    # Initialize GPS service for field mode
    app.state.gps_service = GPSService(
        enable_gps=getattr(app.state.config, "enable_gps", False),
        update_interval=getattr(app.state.config, "gps_update_interval", 5.0),
    )

    # Initialize hardware monitoring service
    app.state.hardware_monitor = HardwareMonitorService(
        check_interval=getattr(app.state.config, "hardware_check_interval", 10.0),
        audio_device_check=getattr(app.state.config, "enable_audio_device_check", True),
        system_resource_check=getattr(app.state.config, "enable_system_resource_check", True),
        gps_check=getattr(app.state.config, "enable_gps_check", False),
    )

    # Initialize MQTT service for IoT integration
    app.state.mqtt_service = MQTTService(
        broker_host=getattr(app.state.config, "mqtt_broker_host", "localhost"),
        broker_port=getattr(app.state.config, "mqtt_broker_port", 1883),
        username=getattr(app.state.config, "mqtt_username", "") or None,
        password=getattr(app.state.config, "mqtt_password", "") or None,
        topic_prefix=getattr(app.state.config, "mqtt_topic_prefix", "birdnet"),
        client_id=getattr(app.state.config, "mqtt_client_id", "birdnet-pi"),
        enable_mqtt=getattr(app.state.config, "enable_mqtt", False),
    )

    # Initialize webhook service for HTTP integrations
    app.state.webhook_service = WebhookService(
        enable_webhooks=getattr(app.state.config, "enable_webhooks", False)
    )

    # Configure webhooks from config
    webhook_urls = getattr(app.state.config, "webhook_urls", [])
    if webhook_urls:
        # Handle both list and string formats for backward compatibility
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        app.state.webhook_service.configure_webhooks_from_urls(webhook_url_list)

    # Initialize and start the FIFO reader service for WebSocket streaming
    fifo_base_path = app.state.file_resolver.get_fifo_base_path()
    livestream_fifo_path = f"{fifo_base_path}/birdnet_audio_livestream.fifo"
    app.state.audio_fifo_reader_service = AudioFifoReaderService(
        livestream_fifo_path, app.state.audio_websocket_service, app.state.spectrogram_service
    )

    # Initialize NotificationService and register listeners
    app.state.notification_service = NotificationService(
        app.state.active_websockets,
        app.state.config,
        app.state.mqtt_service,
        app.state.webhook_service,
    )
    app.state.notification_service.register_listeners()

    # Initialize SQLAdmin
    admin = Admin(app, app.state.db_service.engine)
    app.mount("/admin", admin.app, name="sqladmin")

    class DetectionAdmin(ModelView, model=Detection):
        column_list: ClassVar[list] = [
            Detection.id,
            Detection.species,
            Detection.confidence,
            Detection.timestamp,
        ]
        # Add other configurations as needed

    class AudioFileAdmin(ModelView, model=AudioFile):
        column_list: ClassVar[list] = [
            AudioFile.id,
            AudioFile.file_path,
            AudioFile.duration,
            AudioFile.recording_start_time,
        ]
        # Add other configurations as needed

    admin.add_view(DetectionAdmin)
    admin.add_view(AudioFileAdmin)

    # Start the FIFO reader service
    await app.state.audio_fifo_reader_service.start()

    # Start field mode services
    await app.state.gps_service.start()
    await app.state.hardware_monitor.start()

    # Start IoT services
    await app.state.mqtt_service.start()
    await app.state.webhook_service.start()

    yield

    # Cleanup: Stop services
    await app.state.audio_fifo_reader_service.stop()
    await app.state.gps_service.stop()
    await app.state.hardware_monitor.stop()
    await app.state.mqtt_service.stop()
    await app.state.webhook_service.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router.router)  # Include admin functionality (settings, logs, testing)
app.include_router(audio_router.router)
app.include_router(reporting_router.router)
app.include_router(spectrogram_router.router)
app.include_router(field_mode_router.router)
app.include_router(iot_router.router)  # Include IoT integration router
app.include_router(overview_router.router)
app.include_router(detections_router.router, prefix="/api/detections")
app.include_router(websocket_router.router, prefix="/ws")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """Render the main index page."""
    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {
            "site_name": request.app.state.config.site_name,
            "websocket_url": f"ws://{request.url.hostname}:8000/ws",
        },
    )
