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
            # Notification Configuration
            "apprise_targets": {},
            "webhook_targets": {},
            "notification_title_default": "BirdNET-Pi: {{ common_name }}",
            "notification_body_default": (
                "Detected {{ common_name }} ({{ scientific_name }}) at {{ confidence }}% confidence"
            ),
            "notification_rules": [],
            "notify_quiet_hours_start": "",
            "notify_quiet_hours_end": "",
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
        self._rename_old_fields(config)

        # Add version if missing
        if "config_version" not in config:
            config["config_version"] = self.version

        # Upgrade logging config structure
        self._upgrade_logging_config(config)

        # Migrate old apprise notification fields to new structure
        self._migrate_notifications(config)

        # Ensure new notification fields exist with defaults if missing
        if "apprise_targets" not in config:
            config["apprise_targets"] = {}
        if "webhook_targets" not in config:
            config["webhook_targets"] = {}
        if "notification_rules" not in config:
            config["notification_rules"] = []
        if "notify_quiet_hours_start" not in config:
            config["notify_quiet_hours_start"] = ""
        if "notify_quiet_hours_end" not in config:
            config["notify_quiet_hours_end"] = ""

        return config

    def _rename_old_fields(self, config: dict[str, Any]) -> None:
        """Rename old field names to new ones."""
        if "sf_thresh" in config:
            config["species_confidence_threshold"] = config.pop("sf_thresh")
            print("  Renamed: sf_thresh → species_confidence_threshold")

        if "sensitivity" in config:
            config["sensitivity_setting"] = config.pop("sensitivity")
            print("  Renamed: sensitivity → sensitivity_setting")

    def _upgrade_logging_config(self, config: dict[str, Any]) -> None:
        """Upgrade logging config structure to include new fields."""
        if "logging" in config and isinstance(config["logging"], dict):
            # Ensure new fields exist with defaults
            if "json_logs" not in config["logging"]:
                config["logging"]["json_logs"] = None
            if "include_caller" not in config["logging"]:
                config["logging"]["include_caller"] = False
            if "extra_fields" not in config["logging"]:
                config["logging"]["extra_fields"] = {"service": "birdnet-pi"}

    def _migrate_notifications(self, config: dict[str, Any]) -> None:
        """Migrate old apprise notification fields to new notification structure."""
        rules = []

        # Convert old apprise_input to apprise_targets
        if config.get("apprise_input"):
            # Create single "default" target from old apprise_input
            config["apprise_targets"] = {"default": config["apprise_input"]}

            # Create notification rules from old boolean flags
            rules.extend(self._create_notification_rules(config))

            # Apply species filter if present
            self._apply_species_filter(config, rules)

        # Set notification rules
        if rules:
            config["notification_rules"] = rules

        # Migrate notification templates
        self._migrate_notification_templates(config)

        # Remove old fields after migration
        self._remove_old_notification_fields(config)

    def _create_notification_rules(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Create notification rules based on old boolean flags."""
        rules = []

        if config.get("apprise_notify_each_detection"):
            rules.append(
                {
                    "name": "All Detections",
                    "enabled": True,
                    "service": "apprise",
                    "target": "default",
                    "frequency": {"when": "immediate"},
                    "scope": "all",
                    "include_taxa": {},
                    "exclude_taxa": {},
                    "minimum_confidence": config.get("minimum_time_limit", 0),
                    "title_template": "",
                    "body_template": "",
                }
            )

        if config.get("apprise_notify_new_species"):
            rules.append(
                {
                    "name": "New Species Alert",
                    "enabled": True,
                    "service": "apprise",
                    "target": "default",
                    "frequency": {"when": "immediate"},
                    "scope": "new_ever",
                    "include_taxa": {},
                    "exclude_taxa": {},
                    "minimum_confidence": 0,
                    "title_template": "",
                    "body_template": "",
                }
            )

        if config.get("apprise_notify_new_species_each_day"):
            rules.append(
                {
                    "name": "Daily New Species",
                    "enabled": True,
                    "service": "apprise",
                    "target": "default",
                    "frequency": {"when": "immediate"},
                    "scope": "new_today",
                    "include_taxa": {},
                    "exclude_taxa": {},
                    "minimum_confidence": 0,
                    "title_template": "",
                    "body_template": "",
                }
            )

        if config.get("apprise_weekly_report"):
            rules.append(
                {
                    "name": "Weekly Report",
                    "enabled": True,
                    "service": "apprise",
                    "target": "default",
                    "frequency": {"when": "weekly", "day": 0},
                    "scope": "all",
                    "include_taxa": {},
                    "exclude_taxa": {},
                    "minimum_confidence": 0,
                    "title_template": "",
                    "body_template": "",
                }
            )

        return rules

    def _apply_species_filter(self, config: dict[str, Any], rules: list[dict[str, Any]]) -> None:
        """Apply species filter to all rules if present."""
        if config.get("apprise_only_notify_species_names"):
            # Note: These are common names, will need translation to scientific names
            species_list = [
                s.strip() for s in config["apprise_only_notify_species_names"].split(",")
            ]
            for rule in rules:
                # For now, store as species names
                # notification manager will need to handle translation
                rule["include_taxa"]["species"] = species_list

    def _migrate_notification_templates(self, config: dict[str, Any]) -> None:
        """Migrate notification templates from old fields."""
        if config.get("apprise_notification_title"):
            config["notification_title_default"] = config["apprise_notification_title"]
        elif "notification_title_default" not in config:
            config["notification_title_default"] = "BirdNET-Pi: {{ common_name }}"

        if config.get("apprise_notification_body"):
            config["notification_body_default"] = config["apprise_notification_body"]
        elif "notification_body_default" not in config:
            config["notification_body_default"] = (
                "Detected {{ common_name }} ({{ scientific_name }}) at {{ confidence }}% confidence"
            )

    def _remove_old_notification_fields(self, config: dict[str, Any]) -> None:
        """Remove old apprise notification fields after migration."""
        old_apprise_fields = [
            "apprise_input",
            "apprise_notification_title",
            "apprise_notification_body",
            "apprise_notify_each_detection",
            "apprise_notify_new_species",
            "apprise_notify_new_species_each_day",
            "apprise_weekly_report",
            "apprise_only_notify_species_names",
            "minimum_time_limit",
        ]
        for field in old_apprise_fields:
            config.pop(field, None)

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
