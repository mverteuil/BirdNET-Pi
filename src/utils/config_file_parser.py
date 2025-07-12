import yaml
from BirdNET_Pi.src.models.birdnet_config import BirdNETConfig


class ConfigFileParser:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def load_config(self) -> BirdNETConfig:
        with open(self.config_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Explicitly map config_data to BirdNETConfig fields
        return BirdNETConfig(
            site_name=config_data.get("site_name", "BirdNET-Pi"),
            latitude=float(config_data.get("latitude", 0.0)),
            longitude=float(config_data.get("longitude", 0.0)),
            model=config_data.get("model", "BirdNET_GLOBAL_6K_V2.4_Model_FP16"),
            sf_thresh=float(config_data.get("sf_thresh", 0.03)),
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
