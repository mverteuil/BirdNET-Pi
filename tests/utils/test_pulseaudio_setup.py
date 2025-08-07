"""Tests for PulseAudio setup utility."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.utils.pulseaudio_setup import PulseAudioSetup


@pytest.fixture
def mock_config_dir(tmp_path):
    """Mock configuration directory."""
    return tmp_path / ".config" / "pulse"


class TestPulseAudioSetup:
    """Test PulseAudioSetup utility methods."""

    @patch("birdnetpi.utils.pulseaudio_setup.os.uname")
    def test_is_macos_true(self, mock_uname):
        """Should return True when running on macOS."""
        mock_uname.return_value = MagicMock()
        mock_uname.return_value.sysname = "Darwin"

        assert PulseAudioSetup.is_macos() is True

    @patch("birdnetpi.utils.pulseaudio_setup.os.uname")
    def test_is_macos_false(self, mock_uname):
        """Should return False when not running on macOS."""
        mock_uname.return_value = MagicMock()
        mock_uname.return_value.sysname = "Linux"

        assert PulseAudioSetup.is_macos() is False

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_is_pulseaudio_installed_true(self, mock_run):
        """Should return True when PulseAudio is installed."""
        mock_run.return_value.returncode = 0

        assert PulseAudioSetup.is_pulseaudio_installed() is True
        mock_run.assert_called_once_with(
            ["brew", "list", "pulseaudio"],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_is_pulseaudio_installed_false(self, mock_run):
        """Should return False when PulseAudio is not installed."""
        mock_run.return_value.returncode = 1

        assert PulseAudioSetup.is_pulseaudio_installed() is False

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run", side_effect=FileNotFoundError)
    def test_is_pulseaudio_installed_no_brew(self, mock_run):
        """Should return False when brew is not found."""
        assert PulseAudioSetup.is_pulseaudio_installed() is False

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_install_pulseaudio_success(self, mock_run, mock_is_macos):
        """Should successfully install PulseAudio."""
        mock_run.return_value.returncode = 0

        result = PulseAudioSetup.install_pulseaudio()

        assert result is True
        mock_run.assert_called_once_with(["brew", "install", "pulseaudio"], check=True)

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=False)
    def test_install_pulseaudio_not_macos(self, mock_is_macos):
        """Should raise error when not on macOS."""
        with pytest.raises(RuntimeError, match="only supported on macOS"):
            PulseAudioSetup.install_pulseaudio()

    @patch("birdnetpi.utils.pulseaudio_setup.Path.home")
    def test_get_pulseaudio_config_dir(self, mock_home, tmp_path):
        """Should return and create config directory."""
        mock_home.return_value = tmp_path

        config_dir = PulseAudioSetup.get_pulseaudio_config_dir()

        expected_dir = tmp_path / ".config" / "pulse"
        assert config_dir == expected_dir
        assert config_dir.exists()

    def test_backup_existing_config(self, mock_config_dir):
        """Should backup existing configuration files."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        # Create existing config files
        (mock_config_dir / "default.pa").write_text("existing config")
        (mock_config_dir / "daemon.conf").write_text("existing daemon config")

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            result = PulseAudioSetup.backup_existing_config()

        assert result == mock_config_dir
        assert (mock_config_dir / "default.pa.backup").exists()
        assert (mock_config_dir / "daemon.conf.backup").exists()

    def test_backup_existing_config_no_files(self, mock_config_dir):
        """Should return None when no config files exist."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            result = PulseAudioSetup.backup_existing_config()

        assert result is None

    def test_create_server_config(self, mock_config_dir):
        """Should create server configuration files."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            config_dir = PulseAudioSetup.create_server_config(
                container_ip="192.168.1.100",
                port=4713,
                enable_network=True,
            )

        assert config_dir == mock_config_dir
        assert (mock_config_dir / "default.pa").exists()
        assert (mock_config_dir / "daemon.conf").exists()

        # Check content
        default_pa_content = (mock_config_dir / "default.pa").read_text()
        assert "192.168.1.100" in default_pa_content
        assert "4713" in default_pa_content

    def test_create_auth_cookie(self, mock_config_dir):
        """Should create authentication cookie."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            cookie_path = PulseAudioSetup.create_auth_cookie()

        expected_path = mock_config_dir / "cookie"
        assert cookie_path == expected_path
        assert cookie_path.exists()
        assert cookie_path.stat().st_size == 256
        assert oct(cookie_path.stat().st_mode)[-3:] == "600"

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_start_pulseaudio_server_success(self, mock_run):
        """Should successfully start PulseAudio server."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        success, message = PulseAudioSetup.start_pulseaudio_server()

        assert success is True
        assert "started successfully" in message
        assert mock_run.call_count == 2  # kill + start

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_start_pulseaudio_server_failure(self, mock_run):
        """Should handle PulseAudio server start failure."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # kill command succeeds
            subprocess.CalledProcessError(1, "pulseaudio", stderr="error message"),
        ]

        success, message = PulseAudioSetup.start_pulseaudio_server()

        assert success is False
        assert "error message" in message

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_stop_pulseaudio_server_success(self, mock_run):
        """Should successfully stop PulseAudio server."""
        mock_run.return_value.returncode = 0

        success, message = PulseAudioSetup.stop_pulseaudio_server()

        assert success is True
        assert "stopped successfully" in message

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_test_connection_success(self, mock_run):
        """Should successfully test connection to container."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection("192.168.1.100", 4713)

        assert success is True
        assert "Successfully connected" in message

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_test_connection_failure(self, mock_run):
        """Should handle connection failure."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Connection refused"

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection("192.168.1.100", 4713)

        assert success is False
        assert "Connection refused" in message

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_get_audio_devices(self, mock_run):
        """Should return list of audio devices."""
        mock_run.return_value.stdout = "0\tdevice1\tMicrophone 1\n1\tdevice2\tMicrophone 2"
        mock_run.return_value.returncode = 0

        devices = PulseAudioSetup.get_audio_devices()

        assert len(devices) == 2
        assert devices[0]["id"] == "0"
        assert devices[0]["name"] == "device1"
        assert devices[0]["description"] == "Microphone 1"

    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run", side_effect=FileNotFoundError)
    def test_get_audio_devices_no_pactl(self, mock_run):
        """Should return empty list when pactl is not available."""
        devices = PulseAudioSetup.get_audio_devices()
        assert devices == []

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.backup_existing_config")
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.create_server_config")
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.create_auth_cookie")
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server")
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.start_pulseaudio_server")
    def test_setup_streaming_success(
        self,
        mock_start,
        mock_stop,
        mock_cookie,
        mock_config,
        mock_backup,
        mock_installed,
        mock_macos,
        tmp_path,
    ):
        """Should successfully setup streaming."""
        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")

        success, message = PulseAudioSetup.setup_streaming()

        assert success is True
        assert str(tmp_path) in message
        mock_backup.assert_called_once()
        mock_config.assert_called_once()
        mock_cookie.assert_called_once()

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=False)
    def test_setup_streaming_not_macos(self, mock_macos):
        """Should fail when not on macOS."""
        success, message = PulseAudioSetup.setup_streaming()

        assert success is False
        assert "only supports macOS" in message

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=False,
    )
    def test_setup_streaming_not_installed(self, mock_installed, mock_macos):
        """Should fail when PulseAudio is not installed."""
        success, message = PulseAudioSetup.setup_streaming()

        assert success is False
        assert "not installed" in message

    def test_cleanup_config(self, mock_config_dir):
        """Should clean up configuration files."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        # Create files to be cleaned up
        (mock_config_dir / "default.pa").write_text("config")
        (mock_config_dir / "cookie").write_bytes(b"cookie_data")
        (mock_config_dir / "daemon.conf.backup").write_text("backup")

        with patch(
            "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            with patch(
                "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server",
                return_value=(True, "Stopped"),
            ):
                success, message = PulseAudioSetup.cleanup_config()

        assert success is True
        assert "cleaned up successfully" in message
        assert not (mock_config_dir / "default.pa").exists()
        assert not (mock_config_dir / "cookie").exists()
        assert (mock_config_dir / "daemon.conf").exists()  # Restored from backup

    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir")
    @patch("birdnetpi.utils.pulseaudio_setup.PulseAudioSetup.get_audio_devices")
    @patch("birdnetpi.utils.pulseaudio_setup.subprocess.run")
    def test_get_status(
        self, mock_run, mock_devices, mock_config_dir, mock_installed, mock_macos, tmp_path
    ):
        """Should return current status."""
        mock_config_dir.return_value = tmp_path
        mock_devices.return_value = [{"id": "1", "name": "test", "description": "Test Device"}]
        mock_run.return_value.returncode = 0  # Server running

        # Create config files
        (tmp_path / "default.pa").write_text("config")
        (tmp_path / "cookie").write_bytes(b"cookie")

        status = PulseAudioSetup.get_status()

        assert status["macos"] is True
        assert status["pulseaudio_installed"] is True
        assert status["config_exists"] is True
        assert status["cookie_exists"] is True
        assert status["server_running"] is True
        assert len(status["audio_devices"]) == 1
