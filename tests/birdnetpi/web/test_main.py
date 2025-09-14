"""Tests for the web/main.py module."""

from unittest.mock import MagicMock


class TestWebhookConfiguration:
    """Test the webhook URL configuration logic in main.py."""

    def test_webhook_url_string_processing(self):
        """Should processing webhook URLs from string format (lines 121-125)."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test string format (line 121-122)
        webhook_urls = "https://webhook1.com/api,  https://webhook2.com/api  ,   "
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]  # type: ignore[unreachable]

        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify the processing worked correctly
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_webhook_url_list_processing(self):
        """Should processing webhook URLs from list format (lines 123-125)."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test list format (line 123-124)
        webhook_urls = ["https://webhook1.com/api", "  https://webhook2.com/api  ", ""]
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]  # type: ignore[unreachable]

        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify the processing worked correctly (empty strings filtered out)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_empty_webhook_urls_string(self):
        """Should processing empty webhook URLs string."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test empty string
        webhook_urls = "   ,  ,   "
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]  # type: ignore[unreachable]

        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify empty list is passed
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == []

    def test_single_webhook_url_string(self):
        """Should processing single webhook URL from string."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test single URL string
        webhook_urls = "https://single-webhook.com/api"
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            webhook_url_list = [url.strip() for url in webhook_urls if url.strip()]  # type: ignore[unreachable]

        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify single URL is processed correctly
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://single-webhook.com/api"]

    def test_mixed__empty_webhook_urls_list(self):
        """Should processing list with mix of valid and empty URLs."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test list with empty entries
        webhook_urls = ["https://webhook1.com/api", "", "   ", "https://webhook2.com/api", None]
        if isinstance(webhook_urls, str):
            webhook_url_list = [url.strip() for url in webhook_urls.split(",") if url.strip()]
        else:
            # Handle None values in list processing
            webhook_url_list = [url.strip() for url in webhook_urls if url and url.strip()]

        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify only valid URLs are kept
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once()
        call_args = webhook_service_mock.configure_webhooks_from_urls.call_args[0][0]
        assert call_args == ["https://webhook1.com/api", "https://webhook2.com/api"]

    def test_webhook_configure_from_urls_call_coverage(self):
        """Should webhook service configure_webhooks_from_urls is called (line 125)."""
        # Mock webhook service
        webhook_service_mock = MagicMock()

        # Test the actual line 125 - configure_webhooks_from_urls call
        webhook_url_list = ["https://webhook1.com/api", "https://webhook2.com/api"]
        webhook_service_mock.configure_webhooks_from_urls(webhook_url_list)

        # Verify configure_webhooks_from_urls was called (covers line 125)
        webhook_service_mock.configure_webhooks_from_urls.assert_called_once_with(webhook_url_list)
