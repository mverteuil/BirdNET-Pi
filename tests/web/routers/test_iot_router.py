"""Integration tests for IoT router that exercise real services and models."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.web.routers.iot_router import router


@pytest.fixture
def app_with_iot_services():
    """Create FastAPI app with IoT services."""
    app = FastAPI()

    # Set up app state with real IoT services
    app.state.mqtt_service = MQTTService(
        broker_host="localhost",
        broker_port=1883,
        username=None,
        password=None,
        topic_prefix="birdnet",
        client_id="birdnet-pi-test",
        enable_mqtt=False,  # Disabled for testing to avoid connection attempts
    )

    app.state.webhook_service = WebhookService(enable_webhooks=False)

    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_iot_services):
    """Create test client with real app."""
    return TestClient(app_with_iot_services)


class TestIoTRouterIntegration:
    """Integration tests for IoT router with real services."""

    def test_mqtt_status_endpoint(self, client):
        """Should return MQTT service status."""
        response = client.get("/api/iot/mqtt/status")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        # Check for expected MQTT status fields
        expected_fields = ["enabled", "connected", "broker_host", "broker_port"]
        for field in expected_fields:
            assert field in data

        # With MQTT disabled, should not be connected
        assert data["enabled"] is False
        assert data["connected"] is False
        assert data["broker_host"] == "localhost"
        assert data["broker_port"] == 1883

    def test_webhook_status_endpoint(self, client):
        """Should return webhook service status."""
        response = client.get("/api/iot/webhook/status")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        # Check for expected webhook status fields
        assert "enabled" in data
        assert "webhook_count" in data

        # With webhooks disabled, should show as disabled
        assert data["enabled"] is False

    def test_webhook_config_list_endpoint(self, client):
        """Should return list of webhook configurations."""
        response = client.get("/api/iot/webhook/config")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        # Should return a list (empty initially)
        assert isinstance(data, list)

    def test_mqtt_service_dependency_works(self, client):
        """Should use real MQTTService instance."""
        response = client.get("/api/iot/mqtt/status")

        assert response.status_code == 200

        # The MQTTService should be a real instance
        app = client.app
        mqtt_service = app.state.mqtt_service
        assert isinstance(mqtt_service, MQTTService)

    def test_webhook_service_dependency_works(self, client):
        """Should use real WebhookService instance."""
        response = client.get("/api/iot/webhook/status")

        assert response.status_code == 200

        # The WebhookService should be a real instance
        app = client.app
        webhook_service = app.state.webhook_service
        assert isinstance(webhook_service, WebhookService)

    def test_mqtt_publish_endpoint_structure(self, client):
        """Should handle MQTT publish requests properly."""
        # Test with minimal valid payload
        payload = {"topic": "test/topic", "message": "test message"}

        response = client.post("/api/iot/mqtt/publish", json=payload)

        # With MQTT disabled, this might return an error, but should be properly structured
        assert response.status_code in [200, 400, 503]  # Allow various responses

        if response.status_code != 200:
            # Should return proper error structure
            data = response.json()
            assert "detail" in data

    def test_webhook_add_endpoint_structure(self, client):
        """Should handle webhook addition requests properly."""
        # Test with minimal valid webhook config
        payload = {"url": "https://example.com/webhook", "events": ["detection"]}

        response = client.post("/api/iot/webhook/add", json=payload)

        # Should either succeed or return structured error
        assert response.status_code in [200, 201, 400, 422]

        if response.status_code in [400, 422]:
            # Should return proper error structure
            data = response.json()
            assert "detail" in data

    def test_iot_router_uses_real_pydantic_models(self, client):
        """Should use real Pydantic models for validation."""
        # Test with invalid webhook config to trigger validation
        invalid_payload = {"url": "not-a-valid-url", "events": "not-a-list"}

        response = client.post("/api/iot/webhook/add", json=invalid_payload)

        # Should return 422 for validation error
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data
        # Pydantic validation errors have specific structure
        assert isinstance(data["detail"], list)
