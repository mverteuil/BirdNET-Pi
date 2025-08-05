"""IoT API routes for MQTT and webhook integration management."""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.web.core.container import Container

router = APIRouter()


@router.get("/mqtt/status")
@inject
async def get_mqtt_status(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),
) -> dict:
    """Get MQTT service status."""
    return {
        "enabled": mqtt_service.enable_mqtt,
        "connected": mqtt_service.is_connected if mqtt_service.enable_mqtt else False,
        "broker_host": mqtt_service.broker_host if mqtt_service.enable_mqtt else None,
        "broker_port": mqtt_service.broker_port if mqtt_service.enable_mqtt else None,
    }


@router.get("/webhooks/status")
@inject
async def get_webhook_status(
    webhook_service: WebhookService = Depends(Provide[Container.webhook_service]),
) -> dict:
    """Get webhook service status."""
    return {
        "enabled": webhook_service.enable_webhooks,
        "configured_urls": len(webhook_service.webhooks) if webhook_service.enable_webhooks else 0,
    }


@router.post("/test")
@inject
async def test_iot_services(
    mqtt_service: MQTTService = Depends(Provide[Container.mqtt_service]),
    webhook_service: WebhookService = Depends(Provide[Container.webhook_service]),
) -> dict:
    """Test IoT service connectivity."""
    results = {"mqtt": False, "webhooks": False}

    if mqtt_service.enable_mqtt:
        results["mqtt"] = mqtt_service.is_connected

    if webhook_service.enable_webhooks:
        # Test webhook connectivity (simplified)
        results["webhooks"] = len(webhook_service.webhooks) > 0

    return {"test_results": results}