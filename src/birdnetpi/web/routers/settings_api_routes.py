"""Settings API routes for configuration management and validation."""

from typing import Annotated

import yaml
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request

from birdnetpi.config import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.auth import require_admin
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.admin import SaveConfigResponse, ValidationResponse, YAMLConfigRequest

router = APIRouter()


def _validate_yaml_config_impl(yaml_content: str, path_resolver: PathResolver) -> dict:
    """Validate YAML configuration content internally."""
    try:
        # Parse YAML
        config_data = yaml.safe_load(yaml_content)

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


@router.post("/settings/validate", response_model=ValidationResponse)
@require_admin
@inject
async def validate_yaml_config(
    request: Request,
    config_request: YAMLConfigRequest,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> ValidationResponse:
    """Validate YAML configuration content."""
    result = _validate_yaml_config_impl(config_request.yaml_content, path_resolver)
    return ValidationResponse(**result)


@router.post("/settings/save", response_model=SaveConfigResponse)
@require_admin
@inject
async def save_yaml_config(
    request: Request,
    config_request: YAMLConfigRequest,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> SaveConfigResponse:
    """Save YAML configuration content."""
    try:
        # First validate the YAML using the shared implementation
        validation_result = _validate_yaml_config_impl(config_request.yaml_content, path_resolver)
        if not validation_result["valid"]:
            return SaveConfigResponse(success=False, message=None, error=validation_result["error"])

        # Get config file path
        config_path = path_resolver.get_birdnetpi_config_path()

        # Write the raw YAML content
        with open(config_path, "w") as f:
            f.write(config_request.yaml_content)

        return SaveConfigResponse(
            success=True, message="Configuration saved successfully", error=None
        )

    except Exception as e:
        return SaveConfigResponse(
            success=False, message=None, error=f"Failed to save configuration: {e!s}"
        )
