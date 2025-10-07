"""Tests for PulseAudio tool CLI."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.configure_pulseaudio import cli


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


class TestPulseAudioTool:
    """Test PulseAudio tool commands."""

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.setup_streaming", autospec=True)
    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_container_ip", autospec=True)
    def test_setup_command(self, mock_get_ip, mock_setup, runner):
        """Should successfully run setup command."""
        mock_get_ip.return_value = "192.168.1.100"
        mock_setup.return_value = (True, "Setup completed successfully")

        result = runner.invoke(cli, ["setup", "--container-ip", "192.168.1.100"])

        assert result.exit_code == 0
        assert "Setting up PulseAudio for container streaming" in result.output
        assert "✓ Setup completed successfully" in result.output
        assert "Next steps:" in result.output

        mock_setup.assert_called_once_with(
            container_ip="192.168.1.100",
            port=4713,
            backup_existing=True,
            container_name="birdnet-pi",
        )

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.setup_streaming", autospec=True)
    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_container_ip", autospec=True)
    def test_setup_command_auto_detect(self, mock_get_ip, mock_setup, runner):
        """Should auto-detect container IP when not specified."""
        mock_get_ip.return_value = "172.17.0.2"
        mock_setup.return_value = (True, "Setup completed successfully")

        result = runner.invoke(cli, ["setup"])

        assert result.exit_code == 0
        assert "Auto-detected container IP: 172.17.0.2" in result.output
        mock_get_ip.assert_called_once_with("birdnet-pi")

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.test_connection", autospec=True)
    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_container_ip", autospec=True)
    def test_test_command(self, mock_get_ip, mock_test, runner):
        """Should test connection to container."""
        mock_get_ip.return_value = "192.168.1.100"
        mock_test.return_value = (True, "Connection successful")

        result = runner.invoke(cli, ["test", "--container-ip", "192.168.1.100"])

        assert result.exit_code == 0
        assert "Testing connection to 192.168.1.100:4713" in result.output
        assert "✓ Connection successful" in result.output

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_status", autospec=True)
    def test_status_command(self, mock_status, runner):
        """Should show current status."""
        mock_status.return_value = {
            "macos": True,
            "pulseaudio_installed": True,
            "config_exists": True,
            "cookie_exists": True,
            "server_running": True,
            "config_dir": "/Users/test/.config/pulse",
            "audio_devices": [{"id": 1, "name": "mic1", "description": "MacBook Pro Microphone"}],
        }

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "PulseAudio Setup Status:" in result.output
        assert "Platform: macOS" in result.output
        assert "PulseAudio installed: ✓" in result.output
        assert "MacBook Pro Microphone" in result.output

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_audio_devices", autospec=True)
    def test_devices_command(self, mock_devices, runner):
        """Should list audio devices."""
        mock_devices.return_value = [
            {
                "id": 1,
                "name": "alsa_input.hw_0_0",
                "description": "Built-in Microphone",
            },
            {
                "id": 2,
                "name": "alsa_input.usb",
                "description": "USB Audio Device",
            },
        ]

        result = runner.invoke(cli, ["devices"])

        assert result.exit_code == 0
        assert "Available Audio Input Devices:" in result.output
        assert "Built-in Microphone" in result.output
        assert "USB Audio Device" in result.output

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.cleanup_config", autospec=True)
    def test_cleanup_command_with_force(self, mock_cleanup, runner):
        """Should cleanup configuration with force flag."""
        mock_cleanup.return_value = (True, "Cleanup completed")

        result = runner.invoke(cli, ["cleanup", "--force"])

        assert result.exit_code == 0
        assert "Cleaning up PulseAudio configuration" in result.output
        assert "✓ Cleanup completed" in result.output
        mock_cleanup.assert_called_once()

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.cleanup_config", autospec=True)
    def test_cleanup_command_cancelled(self, mock_cleanup, runner):
        """Should cancel cleanup when user declines."""
        result = runner.invoke(cli, ["cleanup"], input="n\n")

        assert result.exit_code == 0
        assert "Cleanup cancelled" in result.output
        mock_cleanup.assert_not_called()

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.get_container_ip", autospec=True)
    def test_detect_ip_command(self, mock_get_ip, runner):
        """Should detect container IP."""
        mock_get_ip.return_value = "172.17.0.3"

        result = runner.invoke(cli, ["detect-ip", "--container-name", "my-container"])

        assert result.exit_code == 0
        assert "Detecting IP for container 'my-container'" in result.output
        assert "Detected IP: 172.17.0.3" in result.output
        mock_get_ip.assert_called_once_with("my-container")

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.is_macos", autospec=True)
    @patch(
        "birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.is_pulseaudio_installed", autospec=True
    )
    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.install_pulseaudio", autospec=True)
    def test_install_command(self, mock_install, mock_is_installed, mock_is_macos, runner):
        """Should install PulseAudio on macOS."""
        mock_is_macos.return_value = True
        mock_is_installed.return_value = False
        mock_install.return_value = True

        result = runner.invoke(cli, ["install"])

        assert result.exit_code == 0
        assert "Installing PulseAudio via Homebrew" in result.output
        assert "✓ PulseAudio installed successfully" in result.output
        mock_install.assert_called_once()

    @patch("birdnetpi.cli.configure_pulseaudio.PulseAudioSetup.is_macos", autospec=True)
    def test_install_command_not_macos(self, mock_is_macos, runner):
        """Should fail install on non-macOS."""
        mock_is_macos.return_value = False

        result = runner.invoke(cli, ["install"])

        assert result.exit_code == 1
        assert "✗ PulseAudio installation only supported on macOS" in result.output

    def test_main_help(self, runner):
        """Should show help text."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "PulseAudio Setup for Container Streaming" in result.output
        assert "install" in result.output
        assert "setup" in result.output
        assert "test" in result.output
        assert "status" in result.output
        assert "devices" in result.output
        assert "cleanup" in result.output
        assert "detect-ip" in result.output
