import yaml

from birdnetpi.models.birdnet_config import BirdNETConfig


class ConfigFileParser:
    """Parses and manages BirdNET-Pi configuration files in YAML format."""

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path

    def load_config(self) -> BirdNETConfig:
        """Load the configuration from the specified YAML file into a BirdNETConfig object."""
        with open(self.config_path) as f:
            config_data = yaml.safe_load(f)

        # Explicitly map config_data to BirdNETConfig fields
        return BirdNETConfig(
            site_name=config_data.get("site_name", "BirdNET-Pi"),
            latitude=float(config_data.get("latitude", 0.0)),
            longitude=float(config_data.get("longitude", 0.0)),
            model=config_data.get("model", "BirdNET_GLOBAL_6K_V2.4_Model_FP16"),
            sf_thresh=float(config_data.get("sf_thresh", 0.03)),
            audio_format=config_data.get("audio_format", "mp3"),
            extraction_length=float(config_data.get("extraction_length", 6.0)),
            birdweather_id=config_data.get("birdweather_id", ""),
            apprise_input=config_data.get("apprise_input", ""),
            apprise_notification_title=config_data.get(
                "apprise_notification_title", ""
            ),
            apprise_notification_body=config_data.get("apprise_notification_body", ""),
            apprise_notify_each_detection=bool(
                config_data.get("apprise_notify_each_detection", False)
            ),
            apprise_notify_new_species=bool(
                config_data.get("apprise_notify_new_species", False)
            ),
            apprise_notify_new_species_each_day=bool(
                config_data.get("apprise_notify_new_species_each_day", False)
            ),
            apprise_weekly_report=bool(config_data.get("apprise_weekly_report", False)),
            minimum_time_limit=int(config_data.get("minimum_time_limit", 0)),
            flickr_api_key=config_data.get("flickr_api_key", ""),
            flickr_filter_email=config_data.get("flickr_filter_email", ""),
            database_lang=config_data.get("database_lang", "en"),
            timezone=config_data.get("timezone", "UTC"),
            caddy_pwd=config_data.get("caddy_pwd", ""),
            silence_update_indicator=bool(
                config_data.get("silence_update_indicator", False)
            ),
            birdnetpi_url=config_data.get("birdnetpi_url", ""),
            apprise_only_notify_species_names=config_data.get(
                "apprise_only_notify_species_names", ""
            ),
            apprise_only_notify_species_names_2=config_data.get(
                "apprise_only_notify_species_names_2", ""
            ),
        )

    def save_config(self, config: BirdNETConfig) -> None:
        """Save the provided BirdNETConfig object to the specified YAML file."""
        config_data = {
            "site_name": config.site_name,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "model": config.model,
            "sf_thresh": config.sf_thresh,
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
            "timezone": config.timezone,
            "caddy_pwd": config.caddy_pwd,
            "silence_update_indicator": config.silence_update_indicator,
            "birdnetpi_url": config.birdnetpi_url,
            "apprise_only_notify_species_names": config.apprise_only_notify_species_names,
            "apprise_only_notify_species_names_2": config.apprise_only_notify_species_names_2,
        }
        with open(self.config_path, "w") as f:
            yaml.safe_dump(config_data, f, sort_keys=False)
