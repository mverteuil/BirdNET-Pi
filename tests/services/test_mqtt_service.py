"""Tests for the MQTTService."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.models.database_models import Detection
from birdnetpi.services.mqtt_service import MQTTService


@pytest.fixture
def mqtt_service():
    """Create an MQTTService instance for testing."""
    return MQTTService(
        broker_host="test-broker",
        broker_port=1883,
        username="test_user",
        password="test_pass",
        topic_prefix="test_birdnet",
        client_id="test_client",
        enable_mqtt=False,  # Disabled by default for testing
    )


@pytest.fixture
def enabled_mqtt_service():
    """Create an enabled MQTTService instance for testing."""
    return MQTTService(
        broker_host="test-broker",
        broker_port=1883,
        topic_prefix="test_birdnet",
        client_id="test_client",
        enable_mqtt=True,
    )


class TestMQTTService:
    """Test the MQTTService class."""

    def test_initialization_disabled(self, mqtt_service):
        """Test that MQTTService initializes correctly when disabled."""
        service = mqtt_service

        assert service.broker_host == "test-broker"
        assert service.broker_port == 1883
        assert service.username == "test_user"
        assert service.password == "test_pass"
        assert service.topic_prefix == "test_birdnet"
        assert service.client_id == "test_client"
        assert service.enable_mqtt is False
        assert service.client is None
        assert service.is_connected is False
        assert service.connection_retry_count == 0

    def test_initialization_enabled(self, enabled_mqtt_service):
        """Test that MQTTService initializes correctly when enabled."""
        service = enabled_mqtt_service

        assert service.enable_mqtt is True
        assert service.topics["detections"] == "test_birdnet/detections"
        assert service.topics["status"] == "test_birdnet/status"
        assert service.topics["health"] == "test_birdnet/health"
        assert service.topics["gps"] == "test_birdnet/gps"
        assert service.topics["system"] == "test_birdnet/system"
        assert service.topics["config"] == "test_birdnet/config"

    @pytest.mark.asyncio
    async def test_start_disabled(self, mqtt_service):
        """Test starting MQTT service when disabled."""
        await mqtt_service.start()
        assert mqtt_service.client is None
        assert mqtt_service.is_connected is False

    @pytest.mark.asyncio
    async def test_start_enabled(self, enabled_mqtt_service):
        """Test starting MQTT service when enabled."""
        service = enabled_mqtt_service

        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect.return_value = 0  # MQTT_ERR_SUCCESS
            mock_client_class.return_value = mock_client

            await service.start()

            mock_client_class.assert_called_once_with(client_id="test_client")
            mock_client.connect.assert_called_once_with("test-broker", 1883, 60)
            mock_client.loop_start.assert_called_once()
            assert service.client == mock_client

    @pytest.mark.asyncio
    async def test_start__auth(self, enabled_mqtt_service):
        """Test starting MQTT service with authentication."""
        service = enabled_mqtt_service
        service.username = "auth_user"
        service.password = "auth_pass"

        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect.return_value = 0
            mock_client_class.return_value = mock_client

            await service.start()

            mock_client.username_pw_set.assert_called_once_with("auth_user", "auth_pass")

    @pytest.mark.asyncio
    async def test_stop_disabled(self, mqtt_service):
        """Test stopping MQTT service when disabled."""
        await mqtt_service.stop()
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_stop_enabled(self, enabled_mqtt_service):
        """Test stopping MQTT service when enabled."""
        service = enabled_mqtt_service
        mock_client = MagicMock()
        service.client = mock_client
        service.is_connected = True

        with patch.object(service, "_publish_status") as mock_publish:
            await service.stop()

            mock_publish.assert_called_once_with("offline")
            mock_client.disconnect.assert_called_once()
            assert service.is_connected is False
            assert service.client is None

    def test_on_connect(self, enabled_mqtt_service):
        """Test successful MQTT connection callback."""
        service = enabled_mqtt_service

        with patch("asyncio.create_task") as mock_create_task:
            service._on_connect(None, None, None, 0)  # rc=0 means success

            assert service.is_connected is True
            assert service.connection_retry_count == 0
            assert mock_create_task.call_count == 2

    def test_on_connect_failure(self, enabled_mqtt_service):
        """Test failed MQTT connection callback."""
        service = enabled_mqtt_service

        service._on_connect(None, None, None, 1)  # rc=1 means failure

        assert service.is_connected is False

    def test_on_disconnect(self, enabled_mqtt_service):
        """Test MQTT disconnection callback."""
        service = enabled_mqtt_service
        service.is_connected = True

        # Unexpected disconnection
        service._on_disconnect(None, None, 1)
        assert service.is_connected is False

        # Graceful disconnection
        service.is_connected = True
        service._on_disconnect(None, None, 0)
        assert service.is_connected is False

    @pytest.mark.asyncio
    async def test_publish_detection_disabled(self, mqtt_service):
        """Test publishing detection when MQTT is disabled."""
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

        result = await mqtt_service.publish_detection(detection)
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_detection_enabled(self, enabled_mqtt_service):
        """Test publishing detection when MQTT is enabled."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        # Mock successful publish
        mock_result = MagicMock()
        mock_result.rc = 0  # MQTT_ERR_SUCCESS
        service.client.publish.return_value = mock_result

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

        result = await service.publish_detection(detection)

        assert result is True
        service.client.publish.assert_called_once()
        call_args = service.client.publish.call_args
        assert call_args[0][0] == "test_birdnet/detections"  # Topic

        # Verify payload structure
        payload = json.loads(call_args[0][1])
        assert payload["species"] == "Test Bird"
        assert payload["confidence"] == 0.85
        assert payload["location"]["latitude"] == 40.7128
        assert payload["location"]["longitude"] == -74.0060

    @pytest.mark.asyncio
    async def test_publish_gps_location(self, enabled_mqtt_service):
        """Test publishing GPS location."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        mock_result = MagicMock()
        mock_result.rc = 0
        service.client.publish.return_value = mock_result

        result = await service.publish_gps_location(40.7128, -74.0060, 5.0)

        assert result is True
        service.client.publish.assert_called_once()
        call_args = service.client.publish.call_args
        assert call_args[0][0] == "test_birdnet/gps"
        assert call_args[1]["retain"] is True  # GPS should be retained

        payload = json.loads(call_args[0][1])
        assert payload["latitude"] == 40.7128
        assert payload["longitude"] == -74.0060
        assert payload["accuracy"] == 5.0

    @pytest.mark.asyncio
    async def test_publish_system_health(self, enabled_mqtt_service):
        """Test publishing system health data."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        mock_result = MagicMock()
        mock_result.rc = 0
        service.client.publish.return_value = mock_result

        health_data = {
            "cpu_usage": 45.2,
            "memory_usage": 68.5,
            "disk_usage": 23.1,
            "status": "healthy",
        }

        result = await service.publish_system_health(health_data)

        assert result is True
        service.client.publish.assert_called_once()
        call_args = service.client.publish.call_args
        assert call_args[0][0] == "test_birdnet/health"
        assert call_args[1]["retain"] is True  # Health should be retained

        payload = json.loads(call_args[0][1])
        assert payload["cpu_usage"] == 45.2
        assert payload["memory_usage"] == 68.5
        assert payload["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_publish_system_stats(self, enabled_mqtt_service):
        """Test publishing system statistics."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        mock_result = MagicMock()
        mock_result.rc = 0
        service.client.publish.return_value = mock_result

        stats_data = {"uptime": 86400, "processes": 142, "load_average": [0.5, 0.7, 0.8]}

        result = await service.publish_system_stats(stats_data)

        assert result is True
        service.client.publish.assert_called_once()
        call_args = service.client.publish.call_args
        assert call_args[0][0] == "test_birdnet/system"
        assert call_args[1]["qos"] == 0  # System stats use QoS 0

    @pytest.mark.asyncio
    async def test_publish_status(self, enabled_mqtt_service):
        """Test publishing service status."""
        service = enabled_mqtt_service
        service.client = MagicMock()

        mock_result = MagicMock()
        mock_result.rc = 0
        service.client.publish.return_value = mock_result

        result = await service._publish_status("online")

        assert result is True
        call_args = service.client.publish.call_args
        assert call_args[0][0] == "test_birdnet/status"
        assert call_args[1]["retain"] is True  # Status should be retained

        payload = json.loads(call_args[0][1])
        assert payload["status"] == "online"
        assert payload["client_id"] == "test_client"

    @pytest.mark.asyncio
    async def test_publish_system_info(self, enabled_mqtt_service):
        """Test publishing system information."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        mock_result = MagicMock()
        mock_result.rc = 0
        service.client.publish.return_value = mock_result

        # Mock platform and psutil
        with (
            patch("platform.system") as mock_system,
            patch("platform.release") as mock_release,
            patch("platform.machine") as mock_machine,
            patch("platform.node") as mock_node,
            patch("platform.python_version") as mock_python,
            patch("psutil.cpu_count") as mock_cpu_count,
            patch("psutil.virtual_memory") as mock_memory,
        ):
            mock_system.return_value = "Linux"
            mock_release.return_value = "5.4.0"
            mock_machine.return_value = "x86_64"
            mock_node.return_value = "birdnet-pi"
            mock_python.return_value = "3.11.0"
            mock_cpu_count.return_value = 4
            mock_memory.return_value.total = 8589934592

            result = await service._publish_system_info()

            assert result is True
            call_args = service.client.publish.call_args
            assert call_args[0][0] == "test_birdnet/config"

            payload = json.loads(call_args[0][1])
            assert payload["system"]["platform"] == "Linux"
            assert payload["hardware"]["cpu_count"] == 4
            assert payload["mqtt"]["topic_prefix"] == "test_birdnet"

    def test_can_publish(self, enabled_mqtt_service):
        """Test the _can_publish method."""
        service = enabled_mqtt_service

        # Not connected, no client
        assert service._can_publish() is False

        # Connected but no client
        service.is_connected = True
        assert service._can_publish() is False

        # Connected with client
        service.client = MagicMock()
        assert service._can_publish() is True

        # Disabled service
        service.enable_mqtt = False
        assert service._can_publish() is False

    def test_get_connection_status(self, enabled_mqtt_service):
        """Test getting connection status."""
        service = enabled_mqtt_service
        service.is_connected = True
        service.connection_retry_count = 2

        status = service.get_connection_status()

        assert status["enabled"] is True
        assert status["connected"] is True
        assert status["broker_host"] == "test-broker"
        assert status["broker_port"] == 1883
        assert status["client_id"] == "test_client"
        assert status["topic_prefix"] == "test_birdnet"
        assert status["retry_count"] == 2
        assert "detections" in status["topics"]

    @pytest.mark.asyncio
    async def test_publish_failure(self, enabled_mqtt_service):
        """Test handling publish failures."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        # Mock failed publish
        mock_result = MagicMock()
        mock_result.rc = 1  # MQTT_ERR_NOMEM or other error
        service.client.publish.return_value = mock_result

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

        result = await service.publish_detection(detection)
        assert result is False

    @pytest.mark.asyncio
    async def test_publish__exception_handling(self, enabled_mqtt_service):
        """Test exception handling during publish."""
        service = enabled_mqtt_service
        service.client = MagicMock()
        service.is_connected = True

        # Mock exception during publish
        service.client.publish.side_effect = Exception("Connection lost")

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

        result = await service.publish_detection(detection)
        assert result is False

    @pytest.mark.asyncio
    async def test_connection_retry_logic(self, enabled_mqtt_service):
        """Test connection retry logic."""
        service = enabled_mqtt_service

        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            # First attempt fails, second succeeds
            mock_client.connect.side_effect = [Exception("Connection failed"), 0]
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep") as mock_sleep:
                await service.start()

                # Should have called connect twice
                assert mock_client.connect.call_count == 2
                # Should have slept twice: once for retry backoff, once for stabilization
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(5)  # 5 * 1 (first retry)
                mock_sleep.assert_any_call(2)  # Connection stabilization
                mock_client.loop_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, enabled_mqtt_service):
        """Test behavior when max retries are exceeded."""
        service = enabled_mqtt_service

        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect.side_effect = Exception("Connection failed")
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep") as mock_sleep:
                # Start method should not raise (it catches and logs exceptions)
                await service.start()

                # Should have tried max_retries times
                assert mock_client.connect.call_count == service.max_retries
                assert service.connection_retry_count == service.max_retries
                # Should still not be connected
                assert service.is_connected is False
                # Should have slept max_retries - 1 times for backoff (no sleep after last failure)
                assert mock_sleep.call_count == service.max_retries - 1
