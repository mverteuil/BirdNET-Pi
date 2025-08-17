"""Admin API routes for configuration and system management."""

import yaml
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.config import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.admin import YAMLConfigRequest

router = APIRouter()


@router.post("/validate")
@inject
async def validate_yaml_config(
    config_request: YAMLConfigRequest,
    path_resolver: PathResolver = Depends(  # noqa: B008
        Provide[Container.path_resolver]
    ),
) -> dict:
    """Validate YAML configuration content."""
    try:
        # Parse YAML
        config_data = yaml.safe_load(config_request.yaml_content)

        # Create a ConfigManager to leverage the version system
        config_manager = ConfigManager(path_resolver)

        # Get version and apply defaults
        config_version = config_data.get("config_version", "2.0.0")
        version_handler = config_manager.registry.get_version(config_version)

        # Apply defaults from the version system
        config_with_defaults = version_handler.apply_defaults(config_data)

        # Validate using the version handler
        errors = version_handler.validate(config_with_defaults)
        if errors:
            return {"valid": False, "error": f"Validation errors: {', '.join(errors)}"}

        # Try to create the config object to ensure all fields are valid
        config_manager._create_config_object(config_with_defaults)

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
    path_resolver: PathResolver = Depends(  # noqa: B008
        Provide[Container.path_resolver]
    ),
) -> dict:
    """Save YAML configuration content."""
    try:
        # First validate the YAML
        validation_result = await validate_yaml_config(config_request)
        if not validation_result["valid"]:
            return {"success": False, "error": validation_result["error"]}

        # Get config file path
        config_path = path_resolver.get_birdnetpi_config_path()

        # Write the raw YAML content
        with open(config_path, "w") as f:
            f.write(config_request.yaml_content)

        return {"success": True, "message": "Configuration saved successfully"}

    except Exception as e:
        return {"success": False, "error": f"Failed to save configuration: {e!s}"}
