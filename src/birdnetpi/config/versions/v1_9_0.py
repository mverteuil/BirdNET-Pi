"""Configuration version 1.9.0 definition."""

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


class ConfigVersion_1_9_0:  # noqa: N801
    """Configuration version 1.9.0 - Previous version."""

    version = "1.9.0"
    previous_version = None  # This is our oldest tracked version

    @property
    def defaults(self) -> dict[str, Any]:
        """Default values for version 2.4.0."""
        return {
            # Basic Settings
            "site_name": "BirdNET-Pi",
            "latitude": 0.0,
            "longitude": 0.0,
            # Model Configuration (older version)
            "model": "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite",
            "metadata_model": "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite",
            "sf_thresh": 0.03,  # Old field name
            "sensitivity": 1.25,  # Old field name
            # Audio Configuration
            "audio_device_index": -1,
            "sample_rate": 48000,
            "audio_channels": 1,
            # Logging (simpler in 2.4.0)
            "logging": {"level": "INFO"},
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
            # Localization
            "language": "en",
            "species_display_mode": "full",
            "timezone": "UTC",
            # GPS (not in 2.4.0, but adding minimal defaults)
            "enable_gps": False,
            "gps_update_interval": 5.0,
            # Git Update settings
            "git_remote": "origin",
            "git_branch": "main",
        }

    def apply_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply version 1.9.0 defaults to config."""
        return deep_merge(self.defaults, config)

    def upgrade_from_previous(self, config: dict[str, Any]) -> dict[str, Any]:
        """No upgrade needed as this is the oldest version.

        This version represents configs in the v1.9.0 format, which still
        uses the old apprise_input and related fields. The migration to the
        new notification structure happens in v2.0.0.
        """
        # v1.9.0 keeps the old apprise fields as-is
        # The conversion to the new format happens in v2.0.0's upgrade
        return config

    def validate(self, config: dict[str, Any]) -> list[str]:
        """Validate a version 1.9.0 config."""
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

        # Validate sensitivity (old field name)
        if "sensitivity" in config:
            sens = config["sensitivity"]
            if not 0.5 <= sens <= 2.0:
                errors.append(f"sensitivity must be between 0.5 and 2.0, got {sens}")

        # Validate sf_thresh (old field name)
        if "sf_thresh" in config:
            thresh = config["sf_thresh"]
            if not 0.0 <= thresh <= 1.0:
                errors.append(f"sf_thresh must be between 0.0 and 1.0, got {thresh}")

        return errors
