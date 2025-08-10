"""Consolidated configuration models for BirdNET-Pi.

This module contains all configuration-related dataclasses and models
used throughout the application.
"""

from dataclasses import dataclass, field


@dataclass
class LoggingConfig:
    """Structlog-based logging configuration."""

    level: str = "INFO"
    json_logs: bool | None = None  # None = auto-detect based on environment
    include_caller: bool = False  # Include file:line info (useful for debugging)
    extra_fields: dict[str, str] = field(default_factory=lambda: {"service": "birdnet-pi"})


@dataclass
class BirdNETConfig:
    """Represents the configuration settings for the BirdNET-Pi application."""

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
    sample_rate: int = 48000  # Default sample rate
    audio_channels: int = 1  # Default to mono

    # Logging settings
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # BirdWeather
    birdweather_id: str = ""

    # Notifications
    apprise_input: str = ""  # This will store the raw apprise config URLs
    apprise_notification_body: str = ""
    apprise_notification_title: str = ""
    apprise_notify_each_detection: bool = False
    apprise_notify_new_species: bool = False
    apprise_notify_new_species_each_day: bool = False
    apprise_only_notify_species_names: str = ""  # comma separated string
    apprise_weekly_report: bool = False
    minimum_time_limit: int = 0  # Assuming seconds, integer

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
    webhook_urls: list[str] = field(default_factory=list)  # List of webhook URLs
    webhook_events: str = "detection,health,gps,system"  # Events to send via webhooks

    # Git Update settings
    git_remote: str = "origin"  # Git remote name for updates
    git_branch: str = "main"  # Git branch name for updates
