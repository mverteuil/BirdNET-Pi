"""Configuration models for BirdNET-Pi.

This module contains all configuration-related Pydantic models used throughout the application.
"""

from pydantic import BaseModel, Field


class LoggingConfig(BaseModel):
    """Structlog-based logging configuration."""

    level: str = "INFO"
    json_logs: bool | None = None  # None = auto-detect based on environment
    include_caller: bool = False  # Include file:line info (useful for debugging)
    extra_fields: dict[str, str] = Field(default_factory=lambda: {"service": "birdnet-pi"})


class BirdNETConfig(BaseModel):
    """Configuration settings for the BirdNET-Pi application."""

    # Version tracking
    config_version: str = "2.0.0"  # Configuration schema version

    # Basic Settings
    site_name: str = "BirdNET-Pi"
    latitude: float = 0.0
    longitude: float = 0.0

    # Model Configuration
    model: str = "BirdNET_GLOBAL_6K_V2.4_Model_FP16"  # Main detection model filename
    metadata_model: str = "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"  # Metadata model for filtering
    species_confidence_threshold: float = 0.03  # Min confidence threshold for species detection
    sensitivity_setting: float = 1.25  # Audio analysis sensitivity setting
    privacy_threshold: float = 10.0  # Privacy threshold percentage for human detection cutoff

    # Audio Configuration
    audio_device_index: int = -1  # Default to -1 for system default or auto-detection
    sample_rate: int = 48000  # Default sample rate (BirdNET expects 48kHz)
    audio_channels: int = 1  # Default to mono (BirdNET processes mono audio)
    analysis_overlap: float = 0.5  # Overlap in seconds between consecutive audio segments

    # Logging settings
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # BirdWeather
    birdweather_id: str = ""

    # =========== NOTIFICATION CONFIGURATION ===========

    # Service Endpoints (named targets)
    apprise_targets: dict[str, str] = Field(default_factory=dict)
    # Example: {"email": "mailto://...", "discord": "discord://..."}

    webhook_targets: dict[str, str] = Field(default_factory=dict)
    # Example: {"home_assistant": "http://...", "ifttt": "https://..."}

    # Default Message Templates (Jinja2 supported)
    notification_title_default: str = "BirdNET-Pi: {{ common_name }}"
    notification_body_default: str = (
        "Detected {{ common_name }} ({{ scientific_name }}) at {{ confidence }}% confidence"
    )

    # Notification Rules
    notification_rules: list[dict] = Field(default_factory=list)
    # Each rule is a dict with:
    # - name: str (user-friendly name)
    # - enabled: bool (active/inactive)
    # - service: str ("apprise", "webhook", "mqtt")
    # - target: str (target name for apprise/webhook, topic for mqtt)
    # - frequency: dict with "when", optional "time" and "day"
    # - scope: str ("all", "new_ever", "new_today", "new_this_week")
    # - include_taxa: dict with "orders", "families", "genera", "species" lists
    # - exclude_taxa: dict with "orders", "families", "genera", "species" lists
    # - minimum_confidence: int (0 = use detection threshold)
    # - title_template: str (override title, empty = use default)
    # - body_template: str (override body, empty = use default)

    # Global Notification Settings
    notify_quiet_hours_start: str = ""  # "HH:MM" or empty for no quiet hours
    notify_quiet_hours_end: str = ""  # "HH:MM" or empty for no quiet hours

    # Flickr
    flickr_api_key: str = ""
    flickr_filter_email: str = ""

    # Localization and Species Display
    language: str = "en"  # Language code for UI and species name translation
    species_display_mode: str = "full"  # Options: "full", "common_name", "scientific_name"
    timezone: str = "UTC"  # Default from SystemUtils

    # Field mode and GPS settings
    enable_gps: bool = False  # Enable GPS tracking for field deployments
    gps_update_interval: float = 5.0  # GPS update interval in seconds
    hardware_check_interval: float = 10.0  # Hardware monitoring interval in seconds

    # Hardware monitoring settings
    enable_audio_device_check: bool = True  # Enable audio device monitoring
    enable_system_resource_check: bool = True  # Enable system resource monitoring
    enable_gps_check: bool = False  # Enable GPS device monitoring

    # MQTT Integration settings
    enable_mqtt: bool = False  # Enable MQTT publishing
    mqtt_broker_host: str = "localhost"  # MQTT broker hostname
    mqtt_broker_port: int = 1883  # MQTT broker port
    mqtt_username: str = ""  # MQTT username (optional)
    mqtt_password: str = ""  # MQTT password (optional)
    mqtt_topic_prefix: str = "birdnet"  # MQTT topic prefix
    mqtt_client_id: str = "birdnet-pi"  # MQTT client identifier

    # Webhook Integration settings
    enable_webhooks: bool = False  # Enable webhook notifications
    webhook_urls: list[str] = Field(default_factory=list)  # List of webhook URLs
    webhook_events: str = "detection,health,gps,system"  # Events to send via webhooks

    # Git Update settings
    git_remote: str = "origin"  # Git remote name for updates
    git_branch: str = "main"  # Git branch name for updates

    # Detection Processing
    detections_endpoint: str = "http://localhost:8000/api/detections/"  # Where to send detections
