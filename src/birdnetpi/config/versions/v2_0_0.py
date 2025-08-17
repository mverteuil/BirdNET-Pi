"""Configuration version 2.0.0 definition."""

from typing import Any


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    result = base.copy()

    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


class ConfigVersion_2_0_0:  # noqa: N801
    """Configuration version 2.0.0 - Current version with all modern fields."""

    version = "2.0.0"
    previous_version = "1.9.0"

    @property
    def defaults(self) -> dict[str, Any]:
        """Default values for version 2.0.0."""
        return {
            # Version tracking
            "config_version": "2.0.0",
            # Basic Settings
            "site_name": "BirdNET-Pi",
            "latitude": 0.0,
            "longitude": 0.0,
            # Model Configuration (modern field names)
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite",
            "species_confidence_threshold": 0.03,  # Renamed from sf_thresh
            "sensitivity_setting": 1.25,  # Renamed from sensitivity
            "privacy_threshold": 10.0,
            # Audio Configuration
            "audio_device_index": -1,
            "sample_rate": 48000,
            "audio_channels": 1,
            # Enhanced Logging Configuration
            "logging": {
                "level": "INFO",
                "json_logs": None,  # None = auto-detect
                "include_caller": False,
                "extra_fields": {"service": "birdnet-pi"},
            },
            # BirdWeather
            "birdweather_id": "",
            # Notifications
            "apprise_input": "",
            "apprise_notification_body": "",
            "apprise_notification_title": "",
            "apprise_notify_each_detection": False,
            "apprise_notify_new_species": False,
            "apprise_notify_new_species_each_day": False,
            "apprise_only_notify_species_names": "",
            "apprise_weekly_report": False,
            "minimum_time_limit": 0,
            # Flickr
            "flickr_api_key": "",
            "flickr_filter_email": "",
            # Localization and Species Display
            "language": "en",
            "species_display_mode": "full",
            "timezone": "UTC",
            # Field mode and GPS settings
            "enable_gps": False,
            "gps_update_interval": 5.0,
            "hardware_check_interval": 10.0,
            # Hardware monitoring settings
            "enable_audio_device_check": True,
            "enable_system_resource_check": True,
            "enable_gps_check": False,
            # MQTT Integration settings
            "enable_mqtt": False,
            "mqtt_broker_host": "localhost",
            "mqtt_broker_port": 1883,
            "mqtt_username": "",
            "mqtt_password": "",
            "mqtt_topic_prefix": "birdnet",
            "mqtt_client_id": "birdnet-pi",
            # Webhook Integration settings
            "enable_webhooks": False,
            "webhook_urls": [],
            "webhook_events": "detection,health,gps,system",
            # Git Update settings
            "git_remote": "origin",
            "git_branch": "main",
        }

    def apply_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply version 2.0.0 defaults to config."""
        return deep_merge(self.defaults, config)

    def upgrade_from_previous(self, config: dict[str, Any]) -> dict[str, Any]:
        """Upgrade config from 1.9.0 to 2.0.0."""
        # Rename old field names
        if "sf_thresh" in config:
            config["species_confidence_threshold"] = config.pop("sf_thresh")
            print("  Renamed: sf_thresh → species_confidence_threshold")

        if "sensitivity" in config:
            config["sensitivity_setting"] = config.pop("sensitivity")
            print("  Renamed: sensitivity → sensitivity_setting")

        # Add version if missing
        if "config_version" not in config:
            config["config_version"] = self.version

        # Upgrade logging config structure
        if "logging" in config:
            if isinstance(config["logging"], dict):
                # Ensure new fields exist with defaults
                if "json_logs" not in config["logging"]:
                    config["logging"]["json_logs"] = None
                if "include_caller" not in config["logging"]:
                    config["logging"]["include_caller"] = False
                if "extra_fields" not in config["logging"]:
                    config["logging"]["extra_fields"] = {"service": "birdnet-pi"}

        return config

    def validate(self, config: dict[str, Any]) -> list[str]:  # noqa: C901
        """Validate a version 2.0.0 config."""
        errors = []

        # Check required fields
        if "site_name" not in config:
            errors.append("site_name is required")

        # Validate latitude/longitude ranges
        lat = config.get("latitude", 0)
        if not -90 <= lat <= 90:
            errors.append(f"latitude must be between -90 and 90, got {lat}")

        lon = config.get("longitude", 0)
        if not -180 <= lon <= 180:
            errors.append(f"longitude must be between -180 and 180, got {lon}")

        # Validate sensitivity_setting (new field name)
        if "sensitivity_setting" in config:
            sens = config["sensitivity_setting"]
            if not 0.5 <= sens <= 2.0:
                errors.append(f"sensitivity_setting must be between 0.5 and 2.0, got {sens}")

        # Validate species_confidence_threshold (new field name)
        if "species_confidence_threshold" in config:
            thresh = config["species_confidence_threshold"]
            if not 0.0 <= thresh <= 1.0:
                errors.append(
                    f"species_confidence_threshold must be between 0.0 and 1.0, got {thresh}"
                )

        # Validate privacy_threshold (new in 2.0.0)
        if "privacy_threshold" in config:
            privacy = config["privacy_threshold"]
            if privacy < 0:
                errors.append(f"privacy_threshold cannot be negative, got {privacy}")

        # Validate MQTT port if MQTT is enabled
        if config.get("enable_mqtt", False):
            port = config.get("mqtt_broker_port", 1883)
            if not 1 <= port <= 65535:
                errors.append(f"mqtt_broker_port must be between 1 and 65535, got {port}")

        # Validate webhook URLs if webhooks are enabled
        if config.get("enable_webhooks", False):
            urls = config.get("webhook_urls", [])
            if not urls:
                errors.append("webhook_urls cannot be empty when webhooks are enabled")

        return errors
