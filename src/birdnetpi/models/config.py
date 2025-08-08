"""Consolidated configuration models for BirdNET-Pi.

This module contains all configuration-related dataclasses and models
used throughout the application.
"""

from dataclasses import dataclass, field


@dataclass
class DataConfig:
    """Legacy data configuration - now handled by FilePathResolver."""

    # All data paths now resolved via FilePathResolver and environment variables
    pass


@dataclass
class LoggingConfig:
    """Structlog-based logging configuration."""

    level: str = "INFO"
    json_logs: bool | None = None  # None = auto-detect based on environment
    include_caller: bool = False  # Include file:line info (useful for debugging)
    extra_fields: dict[str, str] = field(default_factory=lambda: {"service": "birdnet-pi"})

    # Legacy field for backward compatibility
    log_level: str = "INFO"  # Deprecated: use 'level' instead

    def __post_init__(self) -> None:
        """Handle backward compatibility for log_level."""
        # Use log_level if level is still default and log_level was changed
        if self.level == "INFO" and self.log_level != "INFO":
            self.level = self.log_level


@dataclass
class BirdNETConfig:
    """Represents the configuration settings for the BirdNET-Pi application."""

    # Basic Settings
    site_name: str = "BirdNET-Pi"
    latitude: float = 0.0
    longitude: float = 0.0
    model: str = "BirdNET_GLOBAL_6K_V2.4_Model_FP16"
    metadata_model: str = "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"  # Metadata model filename
    species_confidence_threshold: float = 0.03  # Minimum confidence threshold for species detection
    sensitivity_setting: float = 1.25  # Audio analysis sensitivity setting
    audio_device_index: int = -1  # Default to -1 for system default or auto-detection
    sample_rate: int = 48000  # Default sample rate
    audio_channels: int = 1  # Default to mono

    # Data paths
    data: DataConfig = field(default_factory=DataConfig)

    # Logging settings
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # BirdWeather
    birdweather_id: str = ""

    # Notifications
    apprise_input: str = ""  # This will store the raw apprise config URLs
    apprise_notification_title: str = ""
    apprise_notification_body: str = ""
    apprise_notify_each_detection: bool = False
    apprise_notify_new_species: bool = False
    apprise_notify_new_species_each_day: bool = False
    apprise_weekly_report: bool = False
    minimum_time_limit: int = 0  # Assuming seconds, integer

    # Flickr
    flickr_api_key: str = ""
    flickr_filter_email: str = ""

    # Localization and Species Display
    database_lang: str = "en"  # Renamed from 'language' to avoid conflict with Python keyword
    language_code: str = "en"  # Language code for species name translation (IOC multilingual)
    species_display_mode: str = "full"  # Options: "full", "common_name", "scientific_name"
    timezone: str = "UTC"  # Default from SystemUtils

    # Other settings from legacy configuration files
    caddy_pwd: str = ""  # Used for authentication, but stored in config
    silence_update_indicator: bool = False  # Controls update indicator display
    birdnetpi_url: str = ""  # External URL for web hosting

    # Species filtering
    apprise_only_notify_species_names: str = ""  # comma separated string
    apprise_only_notify_species_names_2: str = ""  # comma separated string

    # Field mode and GPS settings
    enable_gps: bool = False  # Enable GPS tracking for field deployments
    gps_update_interval: float = 5.0  # GPS update interval in seconds
    hardware_check_interval: float = 10.0  # Hardware monitoring interval in seconds

    # Hardware monitoring settings
    enable_audio_device_check: bool = True  # Enable audio device monitoring
    enable_system_resource_check: bool = True  # Enable system resource monitoring
    enable_gps_check: bool = False  # Enable GPS device monitoring

    # Analysis model configuration
    # Removed duplicate - use species_confidence_threshold instead
    privacy_threshold: float = 10.0  # Privacy threshold percentage for human detection cutoff
    # Removed data_model_version - use metadata_model filename instead

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


@dataclass
class CaddyConfig:
    """Configuration for Caddy web server settings."""

    birdnetpi_url: str


@dataclass
class GitUpdateConfig:
    """Configuration for Git repository updates."""

    remote: str = "origin"
    branch: str = "main"


@dataclass
class DailyPlotConfig:
    """Dataclass to hold configuration for the daily plot."""

    resample_sel: str
    species: str


@dataclass
class MultiDayPlotConfig:
    """Configuration for multi-day plot data preparation."""

    resample_sel: str
    species: str
    top_n: int
