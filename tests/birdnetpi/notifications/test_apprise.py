"""Tests for the AppriseService."""

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import apprise
import pytest

from birdnetpi.notifications.apprise import AppriseService


@pytest.fixture
def apprise_service():
    """Create an AppriseService instance for testing (disabled)."""
    return AppriseService(enable_apprise=False)


@pytest.fixture
def enabled_apprise_service():
    """Create an enabled AppriseService instance for testing."""
    return AppriseService(enable_apprise=True)


@pytest.fixture
def enabled_apprise_service_with_add_mock():
    """Create an enabled AppriseService with mocked add() method.

    This fixture mocks the apprise.Apprise.add() method to return True,
    which is necessary for testing configuration without real Apprise URLs.
    """
    service = AppriseService(enable_apprise=True)
    assert service.apprise_obj is not None  # Type narrowing for pyright
    service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)
    service.apprise_obj.notify = MagicMock(spec=MagicMock, return_value=True)
    service.apprise_obj.clear = MagicMock(spec=MagicMock)
    return service


class TestAppriseServiceInitialization:
    """Test AppriseService initialization."""

    def test_init_disabled(self, apprise_service):
        """Should initialize AppriseService correctly when disabled."""
        service = apprise_service

        assert service.enable_apprise is False
        assert service.apprise_obj is None
        assert service.targets == {}
        assert service.stats["total_sent"] == 0
        assert service.stats["total_failed"] == 0
        assert service.stats["targets_count"] == 0

    def test_init_enabled(self, enabled_apprise_service):
        """Should initialize AppriseService correctly when enabled."""
        service = enabled_apprise_service

        assert service.enable_apprise is True
        assert service.apprise_obj is not None
        assert isinstance(service.apprise_obj, apprise.Apprise)
        assert service.targets == {}
        assert service.stats["total_sent"] == 0
        assert service.stats["total_failed"] == 0
        assert service.stats["targets_count"] == 0


class TestAppriseServiceStartStop:
    """Test AppriseService start and stop methods."""

    @pytest.mark.asyncio
    async def test_start_disabled(self, apprise_service, caplog):
        """Should start AppriseService when disabled."""
        caplog.set_level(logging.INFO, logger="birdnetpi.notifications.apprise")

        await apprise_service.start()

        assert "Apprise service disabled" in caplog.text
        assert apprise_service.apprise_obj is None

    @pytest.mark.asyncio
    async def test_start_enabled(self, enabled_apprise_service, caplog):
        """Should start AppriseService when enabled."""
        caplog.set_level(logging.INFO, logger="birdnetpi.notifications.apprise")

        await enabled_apprise_service.start()

        assert "Starting Apprise service" in caplog.text
        assert "Apprise service started with 0 configured targets" in caplog.text

    @pytest.mark.asyncio
    async def test_start_enabled_with_targets(self, enabled_apprise_service, caplog):
        """Should start AppriseService when enabled with configured targets."""
        caplog.set_level(logging.INFO, logger="birdnetpi.notifications.apprise")

        # Configure targets before starting
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        await enabled_apprise_service.start()

        assert "Apprise service started with 1 configured targets" in caplog.text

    @pytest.mark.asyncio
    async def test_stop_disabled(self, apprise_service):
        """Should stop AppriseService when disabled."""
        await apprise_service.stop()
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_stop_enabled(self, enabled_apprise_service, caplog):
        """Should stop AppriseService when enabled."""
        caplog.set_level(logging.INFO, logger="birdnetpi.notifications.apprise")

        await enabled_apprise_service.start()
        await enabled_apprise_service.stop()

        assert "Stopping Apprise service" in caplog.text
        assert "Apprise service stopped" in caplog.text


class TestAppriseServiceConfiguration:
    """Test AppriseService target configuration."""

    def test_configure_targets_disabled(self, apprise_service):
        """Should skip configuration when service is disabled."""
        apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        assert apprise_service.targets == {}
        assert apprise_service.stats["targets_count"] == 0

    def test_configure_targets_enabled_valid(self, enabled_apprise_service, caplog):
        """Should configure valid Apprise targets."""
        caplog.set_level(logging.INFO, logger="birdnetpi.notifications.apprise")

        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        targets = {
            "discord": "discord://webhook_id/webhook_token",
            "slack": "slack://token_a/token_b/token_c",
        }

        enabled_apprise_service.configure_targets(targets)

        assert len(enabled_apprise_service.targets) == 2
        assert "discord" in enabled_apprise_service.targets
        assert "slack" in enabled_apprise_service.targets
        assert enabled_apprise_service.stats["targets_count"] == 2
        assert "Added Apprise target: discord" in caplog.text
        assert "Added Apprise target: slack" in caplog.text

    def test_configure_targets_skip_empty_urls(self, enabled_apprise_service):
        """Should skip empty URLs when configuring targets."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        targets = {
            "discord": "discord://webhook_id/webhook_token",
            "empty": "",
            "whitespace": "   ",
            "telegram": "tgram://bot_token/chat_id",
        }

        enabled_apprise_service.configure_targets(targets)

        assert len(enabled_apprise_service.targets) == 2
        assert "discord" in enabled_apprise_service.targets
        assert "telegram" in enabled_apprise_service.targets
        assert "empty" not in enabled_apprise_service.targets
        assert "whitespace" not in enabled_apprise_service.targets

    def test_configure_targets_invalid_url(self, enabled_apprise_service, caplog):
        """Should handle invalid Apprise URLs."""
        caplog.set_level(logging.ERROR, logger="birdnetpi.notifications.apprise")

        with patch.object(enabled_apprise_service.apprise_obj, "add", return_value=False):
            enabled_apprise_service.configure_targets(
                {
                    "invalid": "not-a-valid-apprise-url",
                }
            )

            assert "invalid" not in enabled_apprise_service.targets
            assert "Failed to add Apprise target 'invalid'" in caplog.text

    def test_configure_targets_exception(self, enabled_apprise_service, caplog):
        """Should handle exceptions during target configuration."""
        caplog.set_level(logging.ERROR, logger="birdnetpi.notifications.apprise")

        with patch.object(
            enabled_apprise_service.apprise_obj, "add", side_effect=Exception("Configuration error")
        ):
            enabled_apprise_service.configure_targets(
                {
                    "failing": "discord://webhook_id/webhook_token",
                }
            )

            assert "failing" not in enabled_apprise_service.targets
            assert "Error adding Apprise target 'failing'" in caplog.text

    def test_configure_targets_clears_existing(self, enabled_apprise_service):
        """Should clear existing targets when reconfiguring."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        # Configure initial targets
        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )
        assert len(enabled_apprise_service.targets) == 1

        # Reconfigure with different targets
        enabled_apprise_service.configure_targets(
            {
                "slack": "slack://token_a/token_b/token_c",
            }
        )

        assert len(enabled_apprise_service.targets) == 1
        assert "discord" not in enabled_apprise_service.targets
        assert "slack" in enabled_apprise_service.targets


class TestAppriseServiceNotifications:
    """Test AppriseService notification sending."""

    @pytest.mark.asyncio
    async def test_send_notification_disabled(self, apprise_service):
        """Should not send notification when service is disabled."""
        result = await apprise_service.send_notification(
            title="Test",
            body="Test message",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_no_targets(self, enabled_apprise_service):
        """Should not send notification when no targets configured."""
        result = await enabled_apprise_service.send_notification(
            title="Test",
            body="Test message",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_success(self, enabled_apprise_service):
        """Should successfully send notification."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", return_value=True
        ) as mock_notify:
            result = await enabled_apprise_service.send_notification(
                title="Test Title",
                body="Test Body",
                notification_type=apprise.NotifyType.INFO,
            )

            assert result is True
            assert enabled_apprise_service.stats["total_sent"] == 1
            assert enabled_apprise_service.stats["total_failed"] == 0
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_to_specific_target(self, enabled_apprise_service):
        """Should send notification to specific target."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
                "slack": "slack://token_a/token_b/token_c",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", return_value=True
        ) as mock_notify:
            result = await enabled_apprise_service.send_notification(
                title="Test",
                body="Test message",
                target_name="discord",
            )

            assert result is True
            # Verify tag was passed to notify
            call_kwargs = mock_notify.call_args[1]
            assert call_kwargs["tag"] == "discord"

    @pytest.mark.asyncio
    async def test_send_notification_failure(self, enabled_apprise_service):
        """Should handle notification sending failure."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=False):
            result = await enabled_apprise_service.send_notification(
                title="Test",
                body="Test message",
            )

            assert result is False
            assert enabled_apprise_service.stats["total_sent"] == 0
            assert enabled_apprise_service.stats["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_send_notification_exception(self, enabled_apprise_service, caplog):
        """Should handle exceptions during notification sending."""
        caplog.set_level(logging.ERROR, logger="birdnetpi.notifications.apprise")

        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", side_effect=Exception("Network error")
        ):
            result = await enabled_apprise_service.send_notification(
                title="Test",
                body="Test message",
            )

            assert result is False
            assert enabled_apprise_service.stats["total_failed"] == 1
            assert "Error sending Apprise notification" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "notification_type",
        [
            pytest.param(apprise.NotifyType.INFO, id="info"),
            pytest.param(apprise.NotifyType.SUCCESS, id="success"),
            pytest.param(apprise.NotifyType.WARNING, id="warning"),
            pytest.param(apprise.NotifyType.FAILURE, id="failure"),
        ],
    )
    async def test_send_notification_types(self, enabled_apprise_service, notification_type):
        """Should send notifications with different notification types."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", return_value=True
        ) as mock_notify:
            result = await enabled_apprise_service.send_notification(
                title="Test",
                body="Test message",
                notification_type=notification_type,
            )

            assert result is True
            call_kwargs = mock_notify.call_args[1]
            assert call_kwargs["notify_type"] == notification_type


class TestAppriseServiceDetectionNotification:
    """Test AppriseService detection notification methods."""

    @pytest.mark.asyncio
    async def test_send_detection_notification_success(
        self, enabled_apprise_service, model_factory
    ):
        """Should successfully send detection notification."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        detection = model_factory.create_detection(
            species_tensor="Testus species_Test Bird",
            scientific_name="Testus species",
            common_name="Test Bird",
            confidence=0.85,
            timestamp=datetime.now(UTC),
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=True):
            result = await enabled_apprise_service.send_detection_notification(
                detection=detection,
                title="Bird Detected: Test Bird",
                body="A Test Bird was detected with 85.0% confidence",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_detection_notification_to_specific_target(
        self, enabled_apprise_service, model_factory
    ):
        """Should send detection notification to specific target."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
                "slack": "slack://token_a/token_b/token_c",
            }
        )

        detection = model_factory.create_detection(
            common_name="Test Bird",
            confidence=0.85,
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", return_value=True
        ) as mock_notify:
            result = await enabled_apprise_service.send_detection_notification(
                detection=detection,
                title="Bird Detected",
                body="Test message",
                target_name="discord",
            )

            assert result is True
            call_kwargs = mock_notify.call_args[1]
            assert call_kwargs["tag"] == "discord"


class TestAppriseServiceTestTarget:
    """Test AppriseService target testing functionality."""

    @pytest.mark.asyncio
    async def test_test_target_service_not_started(self, apprise_service):
        """Should handle testing when service is not started."""
        result = await apprise_service.test_target("discord")

        assert result["success"] is False
        assert result["error"] == "Apprise service not started"

    @pytest.mark.asyncio
    async def test_test_target_not_found(self, enabled_apprise_service):
        """Should handle testing non-existent target."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        result = await enabled_apprise_service.test_target("nonexistent")

        assert result["success"] is False
        assert "Target 'nonexistent' not found" in result["error"]

    @pytest.mark.asyncio
    async def test_test_target_success(self, enabled_apprise_service):
        """Should successfully test a target."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=True):
            result = await enabled_apprise_service.test_target("discord")

            assert result["success"] is True
            assert result["target"] == "discord"
            assert result["message"] == "Test notification sent"

    @pytest.mark.asyncio
    async def test_test_target_failure(self, enabled_apprise_service):
        """Should handle test target failure."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=False):
            result = await enabled_apprise_service.test_target("discord")

            assert result["success"] is False
            assert result["target"] == "discord"
            assert result["message"] == "Test notification failed"

    @pytest.mark.asyncio
    async def test_test_target_exception(self, enabled_apprise_service):
        """Should handle exceptions during target testing."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", side_effect=Exception("Network error")
        ):
            result = await enabled_apprise_service.test_target("discord")

            assert result["success"] is False
            assert result["target"] == "discord"
            assert result["message"] == "Test notification failed"


class TestAppriseServiceStatus:
    """Test AppriseService status methods."""

    def test_can_send_disabled(self, apprise_service):
        """Should validate sending capability when disabled."""
        assert apprise_service._can_send() is False

    def test_can_send_no_apprise_obj(self, enabled_apprise_service):
        """Should validate sending capability when apprise_obj is None."""
        enabled_apprise_service.apprise_obj = None
        assert enabled_apprise_service._can_send() is False

    def test_can_send_no_targets(self, enabled_apprise_service):
        """Should validate sending capability when no targets configured."""
        assert enabled_apprise_service._can_send() is False

    def test_can_send_ready(self, enabled_apprise_service):
        """Should validate sending capability when ready."""
        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        assert enabled_apprise_service._can_send() is True

    def test_get_service_status_disabled(self, apprise_service):
        """Should get service status when disabled."""
        status = apprise_service.get_service_status()

        assert status["enabled"] is False
        assert status["targets_count"] == 0
        assert status["targets"] == []
        assert status["statistics"]["total_sent"] == 0
        assert status["statistics"]["total_failed"] == 0

    def test_get_service_status_enabled_with_targets(self, enabled_apprise_service):
        """Should get service status when enabled with targets."""
        # Mock apprise.Apprise.add() to return True
        enabled_apprise_service.apprise_obj.add = MagicMock(spec=MagicMock, return_value=True)

        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
                "slack": "slack://token_a/token_b/token_c",
            }
        )

        # Simulate some activity
        enabled_apprise_service.stats["total_sent"] = 10
        enabled_apprise_service.stats["total_failed"] = 2

        status = enabled_apprise_service.get_service_status()

        assert status["enabled"] is True
        assert status["targets_count"] == 2
        assert "discord" in status["targets"]
        assert "slack" in status["targets"]
        assert status["statistics"]["total_sent"] == 10
        assert status["statistics"]["total_failed"] == 2


class TestAppriseServiceStatistics:
    """Test AppriseService statistics tracking."""

    @pytest.mark.asyncio
    async def test_statistics_increment_sent(self, enabled_apprise_service):
        """Should increment sent counter on successful send."""
        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=True):
            await enabled_apprise_service.send_notification("Test", "Message")
            await enabled_apprise_service.send_notification("Test", "Message")

        assert enabled_apprise_service.stats["total_sent"] == 2
        assert enabled_apprise_service.stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_statistics_increment_failed(self, enabled_apprise_service):
        """Should increment failed counter on failed send."""
        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(enabled_apprise_service.apprise_obj, "notify", return_value=False):
            await enabled_apprise_service.send_notification("Test", "Message")
            await enabled_apprise_service.send_notification("Test", "Message")

        assert enabled_apprise_service.stats["total_sent"] == 0
        assert enabled_apprise_service.stats["total_failed"] == 2

    @pytest.mark.asyncio
    async def test_statistics_mixed_results(self, enabled_apprise_service):
        """Should track both successful and failed sends."""
        enabled_apprise_service.configure_targets(
            {
                "discord": "discord://webhook_id/webhook_token",
            }
        )

        with patch.object(
            enabled_apprise_service.apprise_obj, "notify", side_effect=[True, False, True, False]
        ):
            await enabled_apprise_service.send_notification("Test", "Message")
            await enabled_apprise_service.send_notification("Test", "Message")
            await enabled_apprise_service.send_notification("Test", "Message")
            await enabled_apprise_service.send_notification("Test", "Message")

        assert enabled_apprise_service.stats["total_sent"] == 2
        assert enabled_apprise_service.stats["total_failed"] == 2
