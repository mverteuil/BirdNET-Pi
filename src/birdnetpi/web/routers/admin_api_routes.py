"""Admin API routes for configuration and system management."""

import yaml
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.core.container import Container

router = APIRouter()


class YAMLConfigRequest(BaseModel):
    """Request model for YAML configuration operations."""

    yaml_content: str


@router.post("/validate")
@inject
async def validate_yaml_config(
    config_request: YAMLConfigRequest,
    file_resolver: FilePathResolver = Depends(  # noqa: B008
        Provide[Container.file_resolver]
    ),
) -> dict:
    """Validate YAML configuration content."""
    try:
        # Parse YAML
        config_data = yaml.safe_load(config_request.yaml_content)

        # Create a temporary ConfigFileParser to validate
        config_parser = ConfigFileParser(file_resolver.get_birdnetpi_config_path())

        # Try to parse into BirdNETConfig model
        # This will validate all fields and types
        BirdNETConfig(
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
            sensitivity_setting=float(config_data.get("sensitivity", 1.25)),
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
            language=config_data.get(
                "language", config_data.get("language_code", config_data.get("database_lang", "en"))
            ),
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
            webhook_urls=config_parser._parse_webhook_urls(config_data.get("webhook_urls", [])),
        )

        return {"valid": True, "message": "Configuration is valid"}

    except yaml.YAMLError as e:
        return {"valid": False, "error": f"YAML syntax error: {e!s}"}
    except ValueError as e:
        return {"valid": False, "error": f"Configuration value error: {e!s}"}
    except Exception as e:
        return {"valid": False, "error": f"Validation error: {e!s}"}


@router.post("/save")
@inject
async def save_yaml_config(
    config_request: YAMLConfigRequest,
    file_resolver: FilePathResolver = Depends(  # noqa: B008
        Provide[Container.file_resolver]
    ),
) -> dict:
    """Save YAML configuration content."""
    try:
        # First validate the YAML
        validation_result = await validate_yaml_config(config_request)
        if not validation_result["valid"]:
            return {"success": False, "error": validation_result["error"]}

        # Get config file path
        config_path = file_resolver.get_birdnetpi_config_path()

        # Write the raw YAML content
        with open(config_path, "w") as f:
            f.write(config_request.yaml_content)

        return {"success": True, "message": "Configuration saved successfully"}

    except Exception as e:
        return {"success": False, "error": f"Failed to save configuration: {e!s}"}
