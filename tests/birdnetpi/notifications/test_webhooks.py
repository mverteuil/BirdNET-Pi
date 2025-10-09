"""Tests for the WebhookService."""

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, create_autospec, patch

import httpx
import pytest

from birdnetpi.notifications.webhooks import WebhookConfig, WebhookService


@pytest.fixture
def webhook_service():
    """Create a WebhookService instance for testing."""
    return WebhookService(enable_webhooks=False)  # Disabled by default for testing


@pytest.fixture
def enabled_webhook_service():
    """Create an enabled WebhookService instance for testing."""
    return WebhookService(enable_webhooks=True)


class TestWebhookConfig:
    """Test the WebhookConfig class."""

    def test_initialization__defaults(self):
        """Should webhookConfig initialization with default values."""
        config = WebhookConfig(url="https://example.com/webhook")

        assert config.url == "https://example.com/webhook"
        assert config.name == "example.com"  # Extracted from URL
        assert config.enabled is True
        assert config.timeout == 10
        assert config.retry_count == 3
        assert config.events == ["detection", "health", "gps", "system"]

    @pytest.mark.parametrize(
        "invalid_url",
        [
            pytest.param("not-a-url", id="no-scheme"),
            pytest.param("://no-scheme", id="missing-scheme"),
            pytest.param("http://", id="no-netloc"),
        ],
    )
    def test_invalid_url(self, invalid_url):
        """Should webhookConfig with invalid URL."""
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url=invalid_url)

    def test_extract_name_from_url(self):
        """Should name extraction from URL."""
        config = WebhookConfig(url="https://api.example.com/webhook/123")
        assert config.name == "api.example.com"

        config = WebhookConfig(url="http://localhost:8080/webhook")
        assert config.name == "localhost:8080"

    def test_should_send_event(self):
        """Should event filtering logic."""
        config = WebhookConfig(url="https://example.com/webhook", events=["detection", "health"])

        assert config.should_send_event("detection") is True
        assert config.should_send_event("health") is True
        assert config.should_send_event("gps") is False
        assert config.should_send_event("system") is False

        # Disabled webhook should never send
        config.enabled = False
        assert config.should_send_event("detection") is False


class TestWebhookService:
    """Test the WebhookService class."""

    def test_initialization(self):
        """Should initialize WebhookService with correct default state."""
        service = WebhookService(enable_webhooks=True)

        # Verify stats are properly initialized
        assert len(service.webhooks) == 0
        assert service.client is None
        assert service.stats["total_sent"] == 0
        assert service.stats["total_failed"] == 0
        assert service.stats["webhooks_count"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "service_fixture,should_create_client",
        [
            pytest.param("webhook_service", False, id="disabled"),
            pytest.param("enabled_webhook_service", True, id="enabled"),
        ],
    )
    async def test_start(self, request, service_fixture, should_create_client):
        """Should starting webhook service for different states."""
        service = request.getfixturevalue(service_fixture)

        with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
            await service.start()

            if should_create_client:
                mock_client_class.assert_called_once()
                assert service.client is not None
            else:
                mock_client_class.assert_not_called()
                assert service.client is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "service_fixture,has_client",
        [
            pytest.param("webhook_service", False, id="disabled"),
            pytest.param("enabled_webhook_service", True, id="enabled"),
        ],
    )
    async def test_stop(self, request, service_fixture, has_client):
        """Should stopping webhook service for different states."""
        service = request.getfixturevalue(service_fixture)

        mock_client = None
        if has_client:
            mock_client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)
            service.client = mock_client

        await service.stop()

        if has_client:
            assert mock_client is not None
            mock_client.aclose.assert_called_once()
        assert service.client is None

    def test_add_webhook(self, enabled_webhook_service):
        """Should adding webhook configuration."""
        service = enabled_webhook_service

        config = WebhookConfig(url="https://example.com/webhook", name="Test")
        service.add_webhook(config)

        assert len(service.webhooks) == 1
        assert service.webhooks[0] == config
        assert service.stats["webhooks_count"] == 1

    def test_remove_webhook(self, enabled_webhook_service):
        """Should removing webhook configuration."""
        service = enabled_webhook_service

        config = WebhookConfig(url="https://example.com/webhook", name="Test")
        service.add_webhook(config)

        # Remove existing webhook
        result = service.remove_webhook("https://example.com/webhook")
        assert result is True
        assert len(service.webhooks) == 0
        assert service.stats["webhooks_count"] == 0

        # Try to remove non-existent webhook
        result = service.remove_webhook("https://nonexistent.com/webhook")
        assert result is False

    def test_configure_webhooks_from_urls(self, enabled_webhook_service):
        """Should configuring webhooks from URL list."""
        service = enabled_webhook_service

        urls = [
            "https://example.com/webhook1",
            "https://api.test.com/webhook2",
            "",  # Empty URL should be skipped
            "   ",  # Whitespace-only URL should be skipped
            "https://third.com/webhook3",
        ]

        service.configure_webhooks_from_urls(urls)

        assert len(service.webhooks) == 3
        assert service.webhooks[0].url == "https://example.com/webhook1"
        assert service.webhooks[1].url == "https://api.test.com/webhook2"
        assert service.webhooks[2].url == "https://third.com/webhook3"

    def test_configure_webhooks___invalid_url(self, enabled_webhook_service):
        """Should configuring webhooks with invalid URLs."""
        service = enabled_webhook_service

        urls = [
            "https://valid.com/webhook",
            "invalid-url",  # This should be skipped due to ValueError
            "https://another-valid.com/webhook",
        ]

        with patch("birdnetpi.notifications.webhooks.logger", autospec=True) as mock_logger:
            service.configure_webhooks_from_urls(urls)

            # Only valid URLs should be added
            assert len(service.webhooks) == 2
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_detection_webhook_disabled(self, webhook_service, model_factory):
        """Should sending detection webhook when service is disabled."""
        detection = model_factory.create_detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
            latitude=63.4591,
            longitude=-19.3647,
            species_confidence_threshold=0.03,
            week=15,
            sensitivity_setting=1.25,
            overlap=0.5,
        )

        await webhook_service.send_detection_webhook(detection)
        # Should not raise any exceptions, but won't send anything

    @pytest.mark.asyncio
    async def test_send_detection_webhook_enabled(self, enabled_webhook_service, model_factory):
        """Should sending detection webhook when service is enabled."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        # Add a webhook
        config = WebhookConfig(url="https://example.com/webhook", events=["detection"])
        service.add_webhook(config)

        detection = model_factory.create_detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
            latitude=63.4591,
            longitude=-19.3647,
            species_confidence_threshold=0.03,
            week=15,
            sensitivity_setting=1.25,
            overlap=0.5,
        )

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            await service.send_detection_webhook(detection)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            webhook_config = call_args[0][0]
            payload = call_args[0][1]

            assert webhook_config.url == "https://example.com/webhook"
            assert payload["event_type"] == "detection"
            assert payload["detection"]["species"] == "Test Bird"
            assert payload["detection"]["confidence"] == 0.85
            assert payload["detection"]["location"]["latitude"] == 63.4591

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type,send_method,test_data,expected_payload_key",
        [
            pytest.param(
                "health",
                "send_health_webhook",
                {"cpu_usage": 45.2, "memory_usage": 68.5, "status": "healthy"},
                "health",
                id="health-event",
            ),
            pytest.param(
                "gps",
                "send_gps_webhook",
                (63.4591, -19.3647, 5.0),
                "location",
                id="gps-event",
            ),
            pytest.param(
                "system",
                "send_system_webhook",
                {"uptime": 86400, "processes": 142, "load_average": [0.5, 0.7, 0.8]},
                "system",
                id="system-event",
            ),
        ],
    )
    async def test_send_webhook_events(
        self, enabled_webhook_service, event_type, send_method, test_data, expected_payload_key
    ):
        """Should send different webhook event types."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        config = WebhookConfig(url="https://example.com/webhook", events=[event_type])
        service.add_webhook(config)

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            method = getattr(service, send_method)
            if event_type == "gps":
                await method(*test_data)
            else:
                await method(test_data)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            payload = call_args[0][1]

            assert payload["event_type"] == event_type
            if event_type == "health":
                assert payload[expected_payload_key]["cpu_usage"] == 45.2
                assert payload[expected_payload_key]["status"] == "healthy"
            elif event_type == "gps":
                assert payload[expected_payload_key]["latitude"] == 63.4591
                assert payload[expected_payload_key]["longitude"] == -19.3647
                assert payload[expected_payload_key]["accuracy"] == 5.0
            elif event_type == "system":
                assert payload[expected_payload_key]["uptime"] == 86400
                assert payload[expected_payload_key]["processes"] == 142

    @pytest.mark.asyncio
    async def test_send_to_multiple_webhooks(self, enabled_webhook_service, model_factory):
        """Should sending to multiple webhooks concurrently."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        # Add multiple webhooks
        config1 = WebhookConfig(url="https://webhook1.com/api", events=["detection"])
        config2 = WebhookConfig(url="https://webhook2.com/api", events=["detection"])
        config3 = WebhookConfig(
            url="https://webhook3.com/api", events=["health"]
        )  # Different event

        service.add_webhook(config1)
        service.add_webhook(config2)
        service.add_webhook(config3)

        detection = model_factory.create_detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
            species_confidence_threshold=0.03,
            week=15,
            sensitivity_setting=1.25,
            overlap=0.5,
        )

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            await service.send_detection_webhook(detection)

            # Should only call the webhooks that handle "detection" events
            assert mock_send.call_count == 2
            assert service.stats["total_sent"] == 2

    @pytest.mark.asyncio
    async def test_send_webhook_request(self, enabled_webhook_service):
        """Should successful webhook request."""
        service = enabled_webhook_service

        # Use MagicMock with spec (not spec_set) because httpx.Response has read-only properties
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)
        mock_client.post.return_value = mock_response
        service.client = mock_client

        config = WebhookConfig(
            url="https://example.com/webhook", headers={"Authorization": "Bearer token"}, timeout=15
        )

        payload = {"test": "data"}

        result = await service._send_webhook_request(config, payload)

        assert result is True
        mock_client.post.assert_called_once_with(
            "https://example.com/webhook",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "BirdNET-Pi/1.0",
                "Authorization": "Bearer token",
            },
            timeout=15,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure_type,side_effect,status_code,retry_count,expected_calls,expected_result",
        [
            pytest.param("http_error", None, 404, 0, 1, False, id="http-404"),
            pytest.param(
                "timeout", TimeoutError("Request timeout"), None, 1, 2, False, id="timeout-retry"
            ),
            pytest.param(
                "exception",
                Exception("Connection error"),
                None,
                0,
                1,
                False,
                id="generic-exception",
            ),
            pytest.param(
                "httpx_timeout",
                httpx.TimeoutException("Timeout"),
                None,
                0,
                1,
                False,
                id="httpx-timeout",
            ),
            pytest.param(
                "httpx_request",
                httpx.RequestError("Connection failed"),
                None,
                0,
                1,
                False,
                id="httpx-request-error",
            ),
        ],
    )
    async def test_send_webhook_request_failures(
        self,
        enabled_webhook_service,
        failure_type,
        side_effect,
        status_code,
        retry_count,
        expected_calls,
        expected_result,
    ):
        """Should handle various webhook request failures."""
        service = enabled_webhook_service

        mock_client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        if side_effect:
            mock_client.post.side_effect = side_effect
        else:
            mock_response = MagicMock(spec=httpx.Response)
            mock_response.status_code = status_code
            mock_response.text = "Error"
            mock_client.post.return_value = mock_response

        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=retry_count)
        payload = {"test": "data"}

        with patch("asyncio.sleep", autospec=True):
            result = await service._send_webhook_request(config, payload)

        assert result is expected_result
        assert mock_client.post.call_count == expected_calls

    def test_can_send(self, enabled_webhook_service):
        """Should validate sending capability via _can_send method."""
        service = enabled_webhook_service

        # No client, no webhooks
        assert service._can_send() is False

        # Client but no webhooks
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)
        assert service._can_send() is False

        # Client and webhooks
        config = WebhookConfig(url="https://example.com/webhook")
        service.add_webhook(config)
        assert service._can_send() is True

        # Disabled service
        service.enable_webhooks = False
        assert service._can_send() is False

    def test_get_webhook_status(self, enabled_webhook_service):
        """Should getting webhook service status."""
        service = enabled_webhook_service

        config1 = WebhookConfig(url="https://webhook1.com/api", name="Webhook 1")
        config2 = WebhookConfig(url="https://webhook2.com/api", name="Webhook 2", enabled=False)
        service.add_webhook(config1)
        service.add_webhook(config2)

        service.stats["total_sent"] = 10
        service.stats["total_failed"] = 2

        status = service.get_webhook_status()

        assert status["enabled"] is True
        assert status["webhook_count"] == 2
        assert len(status["webhooks"]) == 2
        assert status["webhooks"][0]["name"] == "Webhook 1"
        assert status["webhooks"][0]["enabled"] is True
        assert status["webhooks"][1]["name"] == "Webhook 2"
        assert status["webhooks"][1]["enabled"] is False
        assert status["statistics"]["total_sent"] == 10
        assert status["statistics"]["total_failed"] == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "send_result,expected_success",
        [
            pytest.param(True, True, id="success"),
            pytest.param(False, False, id="failure"),
        ],
    )
    async def test_webhook_testing(self, enabled_webhook_service, send_result, expected_success):
        """Should webhook testing functionality for success and failure cases."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        with patch.object(service, "_send_webhook_request", return_value=send_result) as mock_send:
            result = await service.test_webhook("https://example.com/webhook")

            assert result["success"] is expected_success
            assert result["url"] == "https://example.com/webhook"
            if expected_success:
                assert "timestamp" in result
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook__no_client(self, enabled_webhook_service):
        """Should webhook testing when service is not started."""
        service = enabled_webhook_service
        service.client = None

        result = await service.test_webhook("https://example.com/webhook")

        assert result["success"] is False
        assert "error" in result
        assert result["error"] == "Webhook service not started"

    @pytest.mark.asyncio
    async def test_webhook_exception(self, enabled_webhook_service):
        """Should webhook testing with exception."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        with patch.object(service, "_send_webhook_request", side_effect=Exception("Test error")):
            result = await service.test_webhook("https://example.com/webhook")

            assert result["success"] is False
            assert result["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_webhook_request_retry_backoff(self, enabled_webhook_service):
        """Should exponential backoff in webhook request retries."""
        service = enabled_webhook_service

        mock_client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)
        mock_client.post.side_effect = Exception("Connection error")
        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=3)
        payload = {"test": "data"}

        with patch("asyncio.sleep", autospec=True) as mock_sleep:
            result = await service._send_webhook_request(config, payload)

            assert result is False
            assert mock_client.post.call_count == 4  # Initial + 3 retries

            # Check exponential backoff: 2^0=1, 2^1=2, 2^2=4
            expected_sleeps = [1, 2, 4]
            actual_sleeps = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_sleeps == expected_sleeps

    @pytest.mark.asyncio
    async def test_event_filtering(self, enabled_webhook_service):
        """Should webhooks only receive events they're configured for."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)

        # Webhook 1: Only detection events
        config1 = WebhookConfig(url="https://webhook1.com/api", events=["detection"])
        # Webhook 2: Only health events
        config2 = WebhookConfig(url="https://webhook2.com/api", events=["health"])
        # Webhook 3: All events
        config3 = WebhookConfig(
            url="https://webhook3.com/api", events=["detection", "health", "gps", "system"]
        )

        service.add_webhook(config1)
        service.add_webhook(config2)
        service.add_webhook(config3)

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            # Send health event
            await service.send_health_webhook({"status": "healthy"})

            # Should only call webhook2 and webhook3
            assert mock_send.call_count == 2
            called_urls = [call[0][0].url for call in mock_send.call_args_list]
            assert "https://webhook2.com/api" in called_urls
            assert "https://webhook3.com/api" in called_urls
            assert "https://webhook1.com/api" not in called_urls

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method_name,method_args",
        [
            pytest.param("send_health_webhook", ({"status": "healthy"},), id="health-cannot-send"),
            pytest.param("send_gps_webhook", (63.4591, -19.3647, 10.0), id="gps-cannot-send"),
            pytest.param("send_system_webhook", ({"cpu": 50.0},), id="system-cannot-send"),
        ],
    )
    async def test_send_webhook_cannot_send(
        self, enabled_webhook_service, method_name, method_args
    ):
        """Should webhook send methods return early when service cannot send."""
        service = enabled_webhook_service
        # Disable the service to make _can_send() return False
        service.enabled = False

        with patch.object(service, "_send_webhook_request", autospec=True) as mock_send:
            method = getattr(service, method_name)
            await method(*method_args)
            # Should not call _send_webhook_request
            mock_send.assert_not_called()

    async def test_send_to_webhooks__no_client(self, enabled_webhook_service):
        """Should _send_to_webhooks returns early when no client."""
        service = enabled_webhook_service
        service.client = None  # Set client to None

        with patch("birdnetpi.notifications.webhooks.logger", autospec=True) as mock_logger:
            await service._send_to_webhooks("test", {"data": "test"})
            # Should return early without logging (covers line 258)
            mock_logger.debug.assert_not_called()

    async def test_send_to_webhooks__no_relevant_webhooks(self, enabled_webhook_service, caplog):
        """Should _send_to_webhooks logs and returns when no relevant webhooks."""
        service = enabled_webhook_service
        service.client = create_autospec(httpx.AsyncClient, spec_set=True, instance=True)
        service.webhooks = []  # No webhooks configured

        # Set debug level to capture the log
        caplog.set_level(logging.DEBUG, logger="birdnetpi.notifications.webhooks")

        await service._send_to_webhooks("detection", {"data": "test"})
        # Should log debug message and return (covers lines 266-267)
        assert "No webhooks configured for event type: detection" in caplog.text

    async def test_send_webhook_request__no_client(self, enabled_webhook_service):
        """Should _send_webhook_request returns False when no client."""
        service = enabled_webhook_service
        service.client = None
        webhook = WebhookConfig(url="https://example.com")

        result = await service._send_webhook_request(webhook, {"data": "test"})
        # Should return False early (covers line 300)
        assert result is False
