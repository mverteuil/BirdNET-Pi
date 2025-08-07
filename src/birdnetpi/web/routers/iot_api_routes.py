"""IoT Integration API router for MQTT and webhook management.

This module provides REST API endpoints for managing MQTT connections,
webhook configurations, and IoT integration status.
"""

import logging
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookConfig, WebhookService
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class MQTTStatusResponse(BaseModel):
    """MQTT connection status response."""

    enabled: bool
    connected: bool
    broker_host: str
    broker_port: int
    client_id: str
    topic_prefix: str
    retry_count: int
    topics: dict[str, str]


class WebhookConfigRequest(BaseModel):
    """Request model for webhook configuration."""

    url: str = Field(..., description="Webhook URL")
    name: str = Field("", description="Optional webhook name")
    enabled: bool = Field(True, description="Whether webhook is enabled")
    timeout: int = Field(10, ge=1, le=300, description="Timeout in seconds")
    retry_count: int = Field(3, ge=0, le=10, description="Retry attempts")
    events: list[str] = Field(
        default_factory=lambda: ["detection", "health", "gps", "system"],
        description="Event types to send",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        """Validate event types."""
        valid_events = {"detection", "health", "gps", "system", "test"}
        invalid_events = set(v) - valid_events
        if invalid_events:
            raise ValueError(f"Invalid event types: {invalid_events}")
        return v


class WebhookConfigResponse(BaseModel):
    """Response model for webhook configuration."""

    name: str
    url: str
    enabled: bool
    events: list[str]


class WebhookStatusResponse(BaseModel):
    """Webhook service status response."""

    enabled: bool
    webhook_count: int
    webhooks: list[WebhookConfigResponse]
    statistics: dict[str, int]


class WebhookTestRequest(BaseModel):
    """Request model for webhook testing."""

    url: str = Field(..., description="Webhook URL to test")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class WebhookTestResponse(BaseModel):
    """Response model for webhook test results."""

    success: bool
    url: str
    timestamp: str
    error: str | None = None


class IoTStatusResponse(BaseModel):
    """Overall IoT integration status response."""

    mqtt: MQTTStatusResponse
    webhooks: WebhookStatusResponse


# MQTT Endpoints
@router.get("/mqtt/status", response_model=MQTTStatusResponse)
@inject
async def get_mqtt_status(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),  # noqa: B008
) -> MQTTStatusResponse:
    """Get MQTT connection status and configuration."""
    try:
        connection_status = mqtt_service.get_connection_status()
        return MQTTStatusResponse(**connection_status)
    except Exception as e:
        logger.error("Error getting MQTT status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve MQTT status",
        ) from e


@router.post("/mqtt/test")
@inject
async def test_mqtt_connection(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),  # noqa: B008
) -> dict[str, Any]:
    """Test MQTT connection and publish a test message."""
    try:
        if not mqtt_service.enable_mqtt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="MQTT service is disabled"
            )

        if not mqtt_service.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MQTT service is not connected",
            )

        # Publish a test message
        test_payload = {
            "test": True,
            "message": "MQTT connection test from BirdNET-Pi API",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        success = await mqtt_service.publish_system_stats(test_payload)

        if success:
            return {"success": True, "message": "MQTT test message published successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to publish MQTT test message",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error testing MQTT connection: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test MQTT connection",
        ) from e


# Webhook Endpoints
@router.get("/webhooks/status", response_model=WebhookStatusResponse)
@inject
async def get_webhook_status(
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> WebhookStatusResponse:
    """Get webhook service status and configuration."""
    try:
        webhook_status = webhook_service.get_webhook_status()
        return WebhookStatusResponse(**webhook_status)
    except Exception as e:
        logger.error("Error getting webhook status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve webhook status",
        ) from e


@router.post("/webhooks", response_model=WebhookConfigResponse)
@inject
async def add_webhook(
    config: WebhookConfigRequest,
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> WebhookConfigResponse:
    """Add a new webhook configuration."""
    try:
        if not webhook_service.enable_webhooks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook service is disabled"
            )

        # Create webhook configuration
        webhook_config = WebhookConfig(
            url=config.url,
            name=config.name,
            enabled=config.enabled,
            timeout=config.timeout,
            retry_count=config.retry_count,
            events=config.events,
        )

        # Add to service
        webhook_service.add_webhook(webhook_config)

        return WebhookConfigResponse(
            name=webhook_config.name,
            url=webhook_config.url,
            enabled=webhook_config.enabled,
            events=webhook_config.events,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Error adding webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add webhook"
        ) from e


@router.delete("/webhooks")
@inject
async def remove_webhook(
    url: str,
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> dict[str, Any]:
    """Remove a webhook configuration by URL."""
    try:
        if not webhook_service.enable_webhooks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook service is disabled"
            )

        success = webhook_service.remove_webhook(url)

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

        return {"success": True, "message": f"Webhook removed: {url}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error removing webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove webhook"
        ) from e


@router.post("/webhooks/test", response_model=WebhookTestResponse)
@inject
async def test_webhook(
    test_request: WebhookTestRequest,
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> WebhookTestResponse:
    """Test a webhook URL by sending a test payload."""
    try:
        if not webhook_service.enable_webhooks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook service is disabled"
            )

        result = await webhook_service.test_webhook(test_request.url)

        return WebhookTestResponse(
            success=result["success"],
            url=result["url"],
            timestamp=result["timestamp"],
            error=result.get("error"),
        )

    except Exception as e:
        logger.error("Error testing webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to test webhook"
        ) from e


# Overall Status Endpoints
@router.get("/status", response_model=IoTStatusResponse)
@inject
async def get_iot_status(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),  # noqa: B008
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> IoTStatusResponse:
    """Get overall IoT integration status including MQTT and webhooks."""
    try:
        mqtt_status = mqtt_service.get_connection_status()
        webhook_status = webhook_service.get_webhook_status()

        return IoTStatusResponse(
            mqtt=MQTTStatusResponse(**mqtt_status), webhooks=WebhookStatusResponse(**webhook_status)
        )

    except Exception as e:
        logger.error("Error getting IoT status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve IoT status",
        ) from e


# Event Publishing Endpoints (for manual testing/triggering)
@router.post("/publish/test")
@inject
async def publish_test_events(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),  # noqa: B008
    webhook_service: WebhookService = Depends(  # noqa: B008
        Provide[Container.webhook_service]
    ),
) -> dict[str, Any]:
    """Publish test events to both MQTT and webhooks for testing purposes."""
    try:
        results = {"mqtt": False, "webhooks": False}

        # Test MQTT publishing
        if mqtt_service.enable_mqtt and mqtt_service.is_connected:
            test_data = {
                "test": True,
                "message": "Test event from BirdNET-Pi IoT API",
                "source": "api_test",
            }
            results["mqtt"] = await mqtt_service.publish_system_stats(test_data)

        # Test webhook publishing
        if webhook_service.enable_webhooks and webhook_service.webhooks:
            test_health_data = {
                "status": "healthy",
                "test": True,
                "message": "Test health event from BirdNET-Pi IoT API",
            }
            await webhook_service.send_health_webhook(test_health_data)
            results["webhooks"] = True

        return {
            "success": any(results.values()),
            "results": results,
            "message": "Test events published where services are enabled",
        }

    except Exception as e:
        logger.error("Error publishing test events: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish test events",
        ) from e
