from pathlib import Path

import yaml

from birdnetpi.models.config import BirdNETConfig, LoggingConfig
from birdnetpi.utils.file_path_resolver import FilePathResolver


class ConfigFileParser:
    """Parses and manages BirdNET-Pi configuration files in YAML format.

    Supports environment variable configuration and automatic fallback to templates.
    """

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize ConfigFileParser.

        Args:
            config_path: Optional explicit path to config file.
                        If None, uses FilePathResolver with env var support.
        """
        if config_path is None:
            # Use FilePathResolver for env var support and default paths
            file_resolver = FilePathResolver()
            self.config_path = file_resolver.get_birdnetpi_config_path()
            self.template_path = file_resolver.get_config_template_path()
        else:
            self.config_path = config_path
            # Assume template is in same directory structure if explicit path given
            config_dir = Path(config_path).parent.parent
            self.template_path = str(config_dir / "config_templates" / "birdnetpi.yaml")

    def load_config(self) -> BirdNETConfig:
        """Load the configuration from the specified YAML file into a BirdNETConfig object.

        If the config file doesn't exist, copies from template first.
        """
        # Ensure config file exists, copy from template if needed
        self._ensure_config_exists()

        with open(self.config_path) as f:
            config_data = yaml.safe_load(f)

        # Data section is no longer used - paths handled by FilePathResolver

        # Load logging section if present
        logging_section = config_data.get("logging", {})

        # Explicitly map config_data to BirdNETConfig fields
        return BirdNETConfig(
            site_name=config_data.get("site_name", "BirdNET-Pi"),
            latitude=float(config_data.get("latitude", 0.0)),
            longitude=float(config_data.get("longitude", 0.0)),
            model=config_data.get("model", "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite"),
            metadata_model=config_data.get(
                "metadata_model", "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16"
            ),
            species_confidence_threshold=float(
                config_data.get("species_confidence_threshold", config_data.get("sf_thresh", 0.03))
            ),
            confidence=float(config_data.get("confidence", 0.7)),
            sensitivity=float(config_data.get("sensitivity", 1.25)),
            week=int(config_data.get("week", 0)),
            audio_format=config_data.get("audio_format", "mp3"),
            extraction_length=float(config_data.get("extraction_length", 6.0)),
            birdweather_id=config_data.get("birdweather_id", ""),
            apprise_input=config_data.get("apprise_input", ""),
            apprise_notification_title=config_data.get("apprise_notification_title", ""),
            apprise_notification_body=config_data.get("apprise_notification_body", ""),
            apprise_notify_each_detection=bool(
                config_data.get("apprise_notify_each_detection", False)
            ),
            apprise_notify_new_species=bool(config_data.get("apprise_notify_new_species", False)),
            apprise_notify_new_species_each_day=bool(
                config_data.get("apprise_notify_new_species_each_day", False)
            ),
            apprise_weekly_report=bool(config_data.get("apprise_weekly_report", False)),
            minimum_time_limit=int(config_data.get("minimum_time_limit", 0)),
            flickr_api_key=config_data.get("flickr_api_key", ""),
            flickr_filter_email=config_data.get("flickr_filter_email", ""),
            database_lang=config_data.get("database_lang", "en"),
            language_code=config_data.get("language_code", "en"),
            species_display_mode=config_data.get("species_display_mode", "full"),
            timezone=config_data.get("timezone", "UTC"),
            caddy_pwd=config_data.get("caddy_pwd", ""),
            silence_update_indicator=bool(config_data.get("silence_update_indicator", False)),
            birdnetpi_url=config_data.get("birdnetpi_url", ""),
            apprise_only_notify_species_names=config_data.get(
                "apprise_only_notify_species_names", ""
            ),
            apprise_only_notify_species_names_2=config_data.get(
                "apprise_only_notify_species_names_2", ""
            ),
            audio_device_index=int(config_data.get("audio_device_index", -1)),
            sample_rate=int(config_data.get("sample_rate", 48000)),
            audio_channels=int(config_data.get("audio_channels", 1)),
            # Data paths now handled entirely by FilePathResolver based on environment variables
            # Additional config fields
            enable_gps=bool(config_data.get("enable_gps", False)),
            gps_update_interval=float(config_data.get("gps_update_interval", 5.0)),
            hardware_check_interval=float(config_data.get("hardware_check_interval", 10.0)),
            enable_audio_device_check=bool(config_data.get("enable_audio_device_check", True)),
            enable_system_resource_check=bool(
                config_data.get("enable_system_resource_check", True)
            ),
            enable_gps_check=bool(config_data.get("enable_gps_check", False)),
            privacy_threshold=float(config_data.get("privacy_threshold", 10.0)),
            enable_mqtt=bool(config_data.get("enable_mqtt", False)),
            mqtt_broker_host=config_data.get("mqtt_broker_host", "localhost"),
            mqtt_broker_port=int(config_data.get("mqtt_broker_port", 1883)),
            mqtt_username=config_data.get("mqtt_username", ""),
            mqtt_password=config_data.get("mqtt_password", ""),
            mqtt_topic_prefix=config_data.get("mqtt_topic_prefix", "birdnet"),
            mqtt_client_id=config_data.get("mqtt_client_id", "birdnet-pi"),
            enable_webhooks=bool(config_data.get("enable_webhooks", False)),
            webhook_urls=self._parse_webhook_urls(config_data.get("webhook_urls", [])),
            # Logging configuration
            logging=self._parse_logging_config(logging_section),
        )

    def save_config(self, config: BirdNETConfig) -> None:
        """Save the provided BirdNETConfig object to the specified YAML file."""
        # Ensure config directory exists
        config_dir = Path(self.config_path).parent
        config_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "site_name": config.site_name,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "model": config.model,
            "metadata_model": config.metadata_model,
            "species_confidence_threshold": config.species_confidence_threshold,
            "confidence": config.confidence,
            "sensitivity_setting": config.sensitivity_setting,
            "week": config.week,
            "audio_format": config.audio_format,
            "extraction_length": config.extraction_length,
            "birdweather_id": config.birdweather_id,
            "apprise_input": config.apprise_input,
            "apprise_notification_title": config.apprise_notification_title,
            "apprise_notification_body": config.apprise_notification_body,
            "apprise_notify_each_detection": config.apprise_notify_each_detection,
            "apprise_notify_new_species": config.apprise_notify_new_species,
            "apprise_notify_new_species_each_day": config.apprise_notify_new_species_each_day,
            "apprise_weekly_report": config.apprise_weekly_report,
            "minimum_time_limit": config.minimum_time_limit,
            "flickr_api_key": config.flickr_api_key,
            "flickr_filter_email": config.flickr_filter_email,
            "database_lang": config.database_lang,
            "language_code": config.language_code,
            "species_display_mode": config.species_display_mode,
            "timezone": config.timezone,
            "caddy_pwd": config.caddy_pwd,
            "silence_update_indicator": config.silence_update_indicator,
            "birdnetpi_url": config.birdnetpi_url,
            "apprise_only_notify_species_names": config.apprise_only_notify_species_names,
            "apprise_only_notify_species_names_2": config.apprise_only_notify_species_names_2,
            "audio_device_index": config.audio_device_index,
            "sample_rate": config.sample_rate,
            "audio_channels": config.audio_channels,
            # Additional fields
            "enable_gps": config.enable_gps,
            "gps_update_interval": config.gps_update_interval,
            "hardware_check_interval": config.hardware_check_interval,
            "enable_audio_device_check": config.enable_audio_device_check,
            "enable_system_resource_check": config.enable_system_resource_check,
            "enable_gps_check": config.enable_gps_check,
            "privacy_threshold": config.privacy_threshold,
            "enable_mqtt": config.enable_mqtt,
            "mqtt_broker_host": config.mqtt_broker_host,
            "mqtt_broker_port": config.mqtt_broker_port,
            "mqtt_username": config.mqtt_username,
            "mqtt_password": config.mqtt_password,
            "mqtt_topic_prefix": config.mqtt_topic_prefix,
            "mqtt_client_id": config.mqtt_client_id,
            "enable_webhooks": config.enable_webhooks,
            "webhook_urls": config.webhook_urls,
        }

        # Data paths are now managed by FilePathResolver via environment variables
        # No need to save them to config file

        # Add logging section - use modern structlog format
        config_data["logging"] = {
            "level": config.logging.level,
            "json_logs": config.logging.json_logs,
            "include_caller": config.logging.include_caller,
            "extra_fields": config.logging.extra_fields,
        }

        with open(self.config_path, "w") as f:
            yaml.safe_dump(config_data, f, sort_keys=False)

    def _parse_webhook_urls(self, webhook_urls_value: str | list | None) -> list[str]:
        """Parse webhook_urls handling both string and list formats."""
        if isinstance(webhook_urls_value, str):
            # Legacy string format: comma-separated
            return [url.strip() for url in webhook_urls_value.split(",") if url.strip()]
        elif isinstance(webhook_urls_value, list):
            # New list format
            return [str(url).strip() for url in webhook_urls_value if str(url).strip()]
        else:
            # Fallback to empty list
            return []

    def _parse_logging_config(self, logging_section: dict) -> LoggingConfig:
        """Parse logging configuration section."""
        # Parse new structlog fields
        level = logging_section.get("level", logging_section.get("log_level", "INFO"))
        json_logs = logging_section.get("json_logs")
        include_caller = bool(logging_section.get("include_caller", False))
        extra_fields = logging_section.get("extra_fields", {"service": "birdnet-pi"})

        return LoggingConfig(
            # New structlog fields
            level=level,
            json_logs=json_logs,
            include_caller=include_caller,
            extra_fields=extra_fields,
            # Legacy fields for backward compatibility
            syslog_enabled=bool(logging_section.get("syslog_enabled", False)),
            syslog_host=logging_section.get("syslog_host", "localhost"),
            syslog_port=int(logging_section.get("syslog_port", 514)),
            file_logging_enabled=bool(logging_section.get("file_logging_enabled", False)),
            log_file_path=logging_section.get("log_file_path", ""),
            max_log_file_size_mb=int(logging_section.get("max_log_file_size_mb", 10)),
            log_file_backup_count=int(logging_section.get("log_file_backup_count", 5)),
            log_level=logging_section.get("log_level", level),  # For backward compatibility
        )

    def _ensure_config_exists(self) -> None:
        """Ensure configuration file exists, copying from template if necessary."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            # Create config directory
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy from template if it exists
            template_path = Path(self.template_path)
            if template_path.exists():
                import shutil

                shutil.copy2(template_path, config_path)
            else:
                # Create minimal config if template doesn't exist
                minimal_config = {
                    "site_name": "BirdNET-Pi",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
                    "sf_thresh": 0.03,
                    "confidence": 0.7,
                    "sensitivity": 1.25,
                }
                with open(config_path, "w") as f:
                    yaml.safe_dump(minimal_config, f, sort_keys=False)
