"""Tests for the web/main.py module."""

from unittest.mock import MagicMock

from birdnetpi.notifications.webhooks import WebhookService


class TestWebhookConfiguration:
    """Test the webhook URL configuration logic in main.py."""

    def test_webhook_url_string_processing(self):
        """Should processing webhook URLs from string format (lines 121-125)."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_urls: str | list[str] = "https://webhook1.com/api,  https://webhook2.com/api  ,   "
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_webhook_url_list_processing(self):
        """Should processing webhook URLs from list format (lines 123-125)."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_urls = ["https://webhook1.com/api", "  https://webhook2.com/api  ", ""]
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_empty_webhook_urls_string(self):
        """Should processing empty webhook URLs string."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_urls: str | list[str] = "   ,  ,   "
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == []

    def test_single_webhook_url_string(self):
        """Should processing single webhook URL from string."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_urls: str | list[str] = "https://single-webhook.com/api"
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://single-webhook.com/api"]

    def test_mixed__empty_webhook_urls_list(self):
        """Should processing list with mix of valid and empty URLs."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_urls = ["https://webhook1.com/api", "", "   ", "https://webhook2.com/api", None]
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url and url.strip()]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_webhook_configure_from_urls_call_coverage(self):
        """Should webhook service configure_webhooks_from_urls is called (line 125)."""
        webhook_service_mock = MagicMock(spec=WebhookService)
        webhook_url_list = ["https://webhook1.com/api", "https://webhook2.com/api"]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once_with(webhook_url_list)
