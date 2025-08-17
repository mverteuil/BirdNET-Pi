"""Tests for the WebhookService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.models.database_models import Detection
from birdnetpi.notifications.webhook_service import WebhookConfig, WebhookService


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

    def test_initialization(self):
        """Test WebhookConfig initialization."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            name="Test Webhook",
            enabled=True,
            timeout=15,
            retry_count=2,
            events=["detection", "health"],
        )

        assert config.url == "https://example.com/webhook"
        assert config.name == "Test Webhook"
        assert config.enabled is True
        assert config.timeout == 15
        assert config.retry_count == 2
        assert config.events == ["detection", "health"]

    def test_initialization__defaults(self):
        """Test WebhookConfig initialization with default values."""
        config = WebhookConfig(url="https://example.com/webhook")

        assert config.url == "https://example.com/webhook"
        assert config.name == "example.com"  # Extracted from URL
        assert config.enabled is True
        assert config.timeout == 10
        assert config.retry_count == 3
        assert config.events == ["detection", "health", "gps", "system"]

    def test_invalid_url(self):
        """Test WebhookConfig with invalid URL."""
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url="not-a-url")

        # ftp:// has a scheme and netloc, so it won't fail validation
        # Let's test with truly invalid URLs
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url="://no-scheme")

        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url="http://")

    def test_extract_name_from_url(self):
        """Test name extraction from URL."""
        config = WebhookConfig(url="https://api.example.com/webhook/123")
        assert config.name == "api.example.com"

        config = WebhookConfig(url="http://localhost:8080/webhook")
        assert config.name == "localhost:8080"

    def test_should_send_event(self):
        """Test event filtering logic."""
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

    def test_initialization_disabled(self, webhook_service):
        """Test WebhookService initialization when disabled."""
        service = webhook_service

        assert service.enable_webhooks is False
        assert len(service.webhooks) == 0
        assert service.client is None
        assert service.stats["total_sent"] == 0
        assert service.stats["total_failed"] == 0
        assert service.stats["webhooks_count"] == 0

    def test_initialization_enabled(self, enabled_webhook_service):
        """Test WebhookService initialization when enabled."""
        service = enabled_webhook_service

        assert service.enable_webhooks is True
        assert len(service.webhooks) == 0
        assert service.client is None

    @pytest.mark.asyncio
    async def test_start_disabled(self, webhook_service):
        """Test starting webhook service when disabled."""
        await webhook_service.start()
        assert webhook_service.client is None

    @pytest.mark.asyncio
    async def test_start_enabled(self, enabled_webhook_service):
        """Test starting webhook service when enabled."""
        service = enabled_webhook_service

        with patch("httpx.AsyncClient") as mock_client_class:
            await service.start()

            mock_client_class.assert_called_once()
            assert service.client is not None

    @pytest.mark.asyncio
    async def test_stop_disabled(self, webhook_service):
        """Test stopping webhook service when disabled."""
        await webhook_service.stop()
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_stop_enabled(self, enabled_webhook_service):
        """Test stopping webhook service when enabled."""
        service = enabled_webhook_service
        mock_client = AsyncMock()
        service.client = mock_client

        await service.stop()

        mock_client.aclose.assert_called_once()
        assert service.client is None

    def test_add_webhook(self, enabled_webhook_service):
        """Test adding webhook configuration."""
        service = enabled_webhook_service

        config = WebhookConfig(url="https://example.com/webhook", name="Test")
        service.add_webhook(config)

        assert len(service.webhooks) == 1
        assert service.webhooks[0] == config
        assert service.stats["webhooks_count"] == 1

    def test_remove_webhook(self, enabled_webhook_service):
        """Test removing webhook configuration."""
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
        """Test configuring webhooks from URL list."""
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
        """Test configuring webhooks with invalid URLs."""
        service = enabled_webhook_service

        urls = [
            "https://valid.com/webhook",
            "invalid-url",  # This should be skipped due to ValueError
            "https://another-valid.com/webhook",
        ]

        with patch("birdnetpi.notifications.webhook_service.logger") as mock_logger:
            service.configure_webhooks_from_urls(urls)

            # Only valid URLs should be added
            assert len(service.webhooks) == 2
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_detection_webhook_disabled(self, webhook_service):
        """Test sending detection webhook when service is disabled."""
        detection = Detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
            latitude=40.7128,
            longitude=-74.0060,
            species_confidence_threshold=0.03,
            week=15,
            sensitivity_setting=1.25,
            overlap=0.5,
        )

        await webhook_service.send_detection_webhook(detection)
        # Should not raise any exceptions, but won't send anything

    @pytest.mark.asyncio
    async def test_send_detection_webhook_enabled(self, enabled_webhook_service):
        """Test sending detection webhook when service is enabled."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        # Add a webhook
        config = WebhookConfig(url="https://example.com/webhook", events=["detection"])
        service.add_webhook(config)

        detection = Detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
            latitude=40.7128,
            longitude=-74.0060,
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
            assert payload["detection"]["location"]["latitude"] == 40.7128

    @pytest.mark.asyncio
    async def test_send_health_webhook(self, enabled_webhook_service):
        """Test sending health webhook."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        config = WebhookConfig(url="https://example.com/webhook", events=["health"])
        service.add_webhook(config)

        health_data = {"cpu_usage": 45.2, "memory_usage": 68.5, "status": "healthy"}

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            await service.send_health_webhook(health_data)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            payload = call_args[0][1]

            assert payload["event_type"] == "health"
            assert payload["health"]["cpu_usage"] == 45.2
            assert payload["health"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_send_gps_webhook(self, enabled_webhook_service):
        """Test sending GPS webhook."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        config = WebhookConfig(url="https://example.com/webhook", events=["gps"])
        service.add_webhook(config)

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            await service.send_gps_webhook(40.7128, -74.0060, 5.0)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            payload = call_args[0][1]

            assert payload["event_type"] == "gps"
            assert payload["location"]["latitude"] == 40.7128
            assert payload["location"]["longitude"] == -74.0060
            assert payload["location"]["accuracy"] == 5.0

    @pytest.mark.asyncio
    async def test_send_system_webhook(self, enabled_webhook_service):
        """Test sending system webhook."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        config = WebhookConfig(url="https://example.com/webhook", events=["system"])
        service.add_webhook(config)

        system_data = {"uptime": 86400, "processes": 142, "load_average": [0.5, 0.7, 0.8]}

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            await service.send_system_webhook(system_data)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            payload = call_args[0][1]

            assert payload["event_type"] == "system"
            assert payload["system"]["uptime"] == 86400
            assert payload["system"]["processes"] == 142

    @pytest.mark.asyncio
    async def test_send_to_multiple_webhooks(self, enabled_webhook_service):
        """Test sending to multiple webhooks concurrently."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        # Add multiple webhooks
        config1 = WebhookConfig(url="https://webhook1.com/api", events=["detection"])
        config2 = WebhookConfig(url="https://webhook2.com/api", events=["detection"])
        config3 = WebhookConfig(
            url="https://webhook3.com/api", events=["health"]
        )  # Different event

        service.add_webhook(config1)
        service.add_webhook(config2)
        service.add_webhook(config3)

        detection = Detection(
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
        """Test successful webhook request."""
        service = enabled_webhook_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
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
    async def test_send_webhook_request_failure(self, enabled_webhook_service):
        """Test failed webhook request."""
        service = enabled_webhook_service

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=0)  # No retries
        payload = {"test": "data"}

        result = await service._send_webhook_request(config, payload)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_request_timeout(self, enabled_webhook_service):
        """Test webhook request timeout."""
        service = enabled_webhook_service

        mock_client = AsyncMock()
        mock_client.post.side_effect = TimeoutError("Request timeout")
        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=1)
        payload = {"test": "data"}

        with patch("asyncio.sleep") as mock_sleep:
            result = await service._send_webhook_request(config, payload)

            assert result is False
            assert mock_client.post.call_count == 2  # Initial + 1 retry
            mock_sleep.assert_called_once_with(1)  # 2^0 = 1 second backoff

    @pytest.mark.asyncio
    async def test_send_webhook_request_exception(self, enabled_webhook_service):
        """Test webhook request with unexpected exception."""
        service = enabled_webhook_service

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection error")
        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=0)
        payload = {"test": "data"}

        result = await service._send_webhook_request(config, payload)

        assert result is False

    def test_can_send(self, enabled_webhook_service):
        """Test the _can_send method."""
        service = enabled_webhook_service

        # No client, no webhooks
        assert service._can_send() is False

        # Client but no webhooks
        service.client = AsyncMock()
        assert service._can_send() is False

        # Client and webhooks
        config = WebhookConfig(url="https://example.com/webhook")
        service.add_webhook(config)
        assert service._can_send() is True

        # Disabled service
        service.enable_webhooks = False
        assert service._can_send() is False

    def test_get_webhook_status(self, enabled_webhook_service):
        """Test getting webhook service status."""
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
    async def test_webhook(self, enabled_webhook_service):
        """Test webhook testing functionality - success case."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        with patch.object(service, "_send_webhook_request", return_value=True) as mock_send:
            result = await service.test_webhook("https://example.com/webhook")

            assert result["success"] is True
            assert result["url"] == "https://example.com/webhook"
            assert "timestamp" in result
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_failure(self, enabled_webhook_service):
        """Test webhook testing functionality - failure case."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        with patch.object(service, "_send_webhook_request", return_value=False):
            result = await service.test_webhook("https://example.com/webhook")

            assert result["success"] is False
            assert result["url"] == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_webhook__no_client(self, enabled_webhook_service):
        """Test webhook testing when service is not started."""
        service = enabled_webhook_service
        service.client = None

        result = await service.test_webhook("https://example.com/webhook")

        assert result["success"] is False
        assert "error" in result
        assert result["error"] == "Webhook service not started"

    @pytest.mark.asyncio
    async def test_webhook_exception(self, enabled_webhook_service):
        """Test webhook testing with exception."""
        service = enabled_webhook_service
        service.client = AsyncMock()

        with patch.object(service, "_send_webhook_request", side_effect=Exception("Test error")):
            result = await service.test_webhook("https://example.com/webhook")

            assert result["success"] is False
            assert result["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_webhook_request_retry_backoff(self, enabled_webhook_service):
        """Test exponential backoff in webhook request retries."""
        service = enabled_webhook_service

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection error")
        service.client = mock_client

        config = WebhookConfig(url="https://example.com/webhook", retry_count=3)
        payload = {"test": "data"}

        with patch("asyncio.sleep") as mock_sleep:
            result = await service._send_webhook_request(config, payload)

            assert result is False
            assert mock_client.post.call_count == 4  # Initial + 3 retries

            # Check exponential backoff: 2^0=1, 2^1=2, 2^2=4
            expected_sleeps = [1, 2, 4]
            actual_sleeps = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_sleeps == expected_sleeps

    @pytest.mark.asyncio
    async def test_event_filtering(self, enabled_webhook_service):
        """Test that webhooks only receive events they're configured for."""
        service = enabled_webhook_service
        service.client = AsyncMock()

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

    async def test_send_health_webhook__cannot_send(self, enabled_webhook_service):
        """Test send_health_webhook returns early when service cannot send."""
        service = enabled_webhook_service

        # Disable the service to make _can_send() return False
        service.enabled = False

        with patch.object(service, "_send_webhook_request") as mock_send:
            await service.send_health_webhook({"status": "healthy"})
            # Should not call _send_webhook_request (covers line 198)
            mock_send.assert_not_called()

    async def test_send_gps_webhook__cannot_send(self, enabled_webhook_service):
        """Test send_gps_webhook returns early when service cannot send."""
        service = enabled_webhook_service

        # Disable the service to make _can_send() return False
        service.enabled = False

        with patch.object(service, "_send_webhook_request") as mock_send:
            await service.send_gps_webhook(40.7128, -74.0060, 10.0)
            # Should not call _send_webhook_request (covers line 219)
            mock_send.assert_not_called()

    async def test_send_system_webhook__cannot_send(self, enabled_webhook_service):
        """Test send_system_webhook returns early when service cannot send."""
        service = enabled_webhook_service

        # Disable the service to make _can_send() return False
        service.enabled = False

        with patch.object(service, "_send_webhook_request") as mock_send:
            await service.send_system_webhook({"cpu": 50.0})
            # Should not call _send_webhook_request (covers line 240)
            mock_send.assert_not_called()

    async def test_send_to_webhooks__no_client(self, enabled_webhook_service):
        """Test _send_to_webhooks returns early when no client."""
        service = enabled_webhook_service
        service.client = None  # Set client to None

        with patch("birdnetpi.notifications.webhook_service.logger") as mock_logger:
            await service._send_to_webhooks("test", {"data": "test"})
            # Should return early without logging (covers line 258)
            mock_logger.debug.assert_not_called()

    async def test_send_to_webhooks__no_relevant_webhooks(self, enabled_webhook_service, caplog):
        """Test _send_to_webhooks logs and returns when no relevant webhooks."""
        import logging

        service = enabled_webhook_service
        service.client = AsyncMock()
        service.webhooks = []  # No webhooks configured

        # Set debug level to capture the log
        caplog.set_level(logging.DEBUG, logger="birdnetpi.notifications.webhook_service")

        await service._send_to_webhooks("detection", {"data": "test"})
        # Should log debug message and return (covers lines 266-267)
        assert "No webhooks configured for event type: detection" in caplog.text

    async def test_send_webhook_request__no_client(self, enabled_webhook_service):
        """Test _send_webhook_request returns False when no client."""
        service = enabled_webhook_service
        service.client = None
        webhook = WebhookConfig(url="https://example.com")

        result = await service._send_webhook_request(webhook, {"data": "test"})
        # Should return False early (covers line 300)
        assert result is False

    async def test_send_webhook_request_timeout_exception(self, enabled_webhook_service, caplog):
        """Test _send_webhook_request handles timeout exception."""
        import httpx

        service = enabled_webhook_service
        webhook = WebhookConfig(url="https://example.com", retry_count=0)

        # Mock client to raise TimeoutException
        service.client = AsyncMock()
        service.client.post.side_effect = httpx.TimeoutException("Timeout")

        result = await service._send_webhook_request(webhook, {"data": "test"})
        # Should log timeout warning and return False (covers line 336)
        assert "Webhook timeout" in caplog.text
        assert result is False

    async def test_send_webhook_request_request__error_exception(
        self, enabled_webhook_service, caplog
    ):
        """Test _send_webhook_request handles request error exception."""
        import httpx

        service = enabled_webhook_service
        webhook = WebhookConfig(url="https://example.com", retry_count=0)

        # Mock client to raise RequestError
        service.client = AsyncMock()
        service.client.post.side_effect = httpx.RequestError("Connection failed")

        result = await service._send_webhook_request(webhook, {"data": "test"})
        # Should log request error warning and return False (covers line 343)
        assert "Webhook request error" in caplog.text
        assert result is False
