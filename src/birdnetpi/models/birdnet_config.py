from dataclasses import dataclass, field


@dataclass
class DataConfig:
    """Configuration for data storage paths."""

    recordings_dir: str = "/mnt/birdnet/recordings"
    extracted_dir: str = "/mnt/birdnet/extracted"
    processed_dir: str = "/mnt/birdnet/processed"
    id_file: str = "/var/log/birdnet/id.txt"
    bird_db_file: str = "/var/log/birdnet/BirdDB.txt"
    db_path: str = "/var/log/birdnet/birdnetpi.db"


@dataclass
class LoggingConfig:
    """Configuration for logging settings."""

    syslog_enabled: bool = False
    syslog_host: str = "localhost"
    syslog_port: int = 514
    file_logging_enabled: bool = False
    log_file_path: str = "~/BirdNET-Pi/birdnetpi.log"
    max_log_file_size_mb: int = 10  # 10 MB
    log_file_backup_count: int = 5
    log_level: str = "INFO"


@dataclass
class BirdNETConfig:
    """Represents the configuration settings for the BirdNET-Pi application."""

    # Basic Settings
    site_name: str = "BirdNET-Pi"
    latitude: float = 0.0
    longitude: float = 0.0
    model: str = "BirdNET_GLOBAL_6K_V2.4_Model_FP16"
    sf_thresh: float = 0.03  # Default from config.php example
    confidence: float = 0.7  # Default from birdnet.conf.template
    sensitivity: float = 1.25  # Default from birdnet.conf.template
    week: int = 0  # Default from birdnet.conf.template
    audio_format: str = "mp3"  # Default from birdnet.conf.template
    extraction_length: float = 6.0  # Default from birdnet.conf.template
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

    # Localization
    database_lang: str = "en"  # Renamed from 'language' to avoid conflict with Python keyword
    timezone: str = "UTC"  # Default from SystemUtils

    # Other settings from config.php / views.php that are read from config files
    caddy_pwd: str = ""  # Used for authentication, but stored in config
    silence_update_indicator: bool = False  # From views.php
    birdnetpi_url: str = ""  # From views.php

    # Species filtering
    apprise_only_notify_species_names: str = ""  # comma separated string
    apprise_only_notify_species_names_2: str = ""  # comma separated string
