"""Tests for PulseAudio setup wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.pulseaudio_setup_wrapper import (
    cleanup_command,
    detect_ip_command,
    devices_command,
    install_command,
    main,
    setup_command,
    status_command,
    test_command,
)


@pytest.fixture
def mock_args():
    """Mock argparse.Namespace object."""
    return MagicMock()


class TestPulseAudioSetupWrapper:
    """Test PulseAudio setup wrapper commands."""

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.setup_streaming")
    @patch("builtins.print")
    def test_setup_command(self, mock_print, mock_setup):
        """Should successfully run setup command."""
        mock_args = MagicMock()
        mock_args.container_ip = "192.168.1.100"
        mock_args.container_name = "birdnet-pi"
        mock_args.port = 4713
        mock_args.no_backup = False

        mock_setup.return_value = (True, "Setup completed successfully")

        setup_command(mock_args)

        mock_setup.assert_called_once_with(
            container_ip="192.168.1.100",
            port=4713,
            backup_existing=True,
            container_name="birdnet-pi",
        )

        # Verify success message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("✓" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.setup_streaming")
    @patch("builtins.print")
    def test_setup_command__auto_detect_ip(self, mock_print, mock_setup, mock_get_ip):
        """Should auto-detect container IP when not provided."""
        mock_args = MagicMock()
        mock_args.container_ip = None
        mock_args.container_name = "test-container"
        mock_args.port = 4713
        mock_args.no_backup = False

        mock_get_ip.return_value = "172.18.0.9"
        mock_setup.return_value = (True, "Setup completed successfully")

        setup_command(mock_args)

        mock_get_ip.assert_called_once_with("test-container")
        mock_setup.assert_called_once_with(
            container_ip=None,
            port=4713,
            backup_existing=True,
            container_name="test-container",
        )

        # Verify auto-detected IP was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Auto-detected container IP: 172.18.0.9" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.setup_streaming")
    @patch("builtins.print")
    def test_setup_command__explicit_ip_no_auto_detect(self, mock_print, mock_setup):
        """Should not auto-detect when explicit IP is provided."""
        mock_args = MagicMock()
        mock_args.container_ip = "10.0.0.4"
        mock_args.container_name = "test-container"
        mock_args.port = 4713
        mock_args.no_backup = False

        mock_setup.return_value = (True, "Setup completed successfully")

        with patch(
            "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip"
        ) as mock_get_ip:
            setup_command(mock_args)
            mock_get_ip.assert_not_called()  # Should not auto-detect

        # Verify explicit IP was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Container IP: 10.0.0.4" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.setup_streaming")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.sys.exit")
    @patch("builtins.print")
    def test_setup_command_failure(self, mock_print, mock_exit, mock_setup):
        """Should handle setup command failure."""
        mock_args = MagicMock()
        mock_args.container_ip = "127.0.0.1"
        mock_args.container_name = "birdnet-pi"
        mock_args.port = 4713
        mock_args.no_backup = False

        mock_setup.return_value = (False, "Setup failed")

        setup_command(mock_args)

        mock_exit.assert_called_once_with(1)

        # Verify error message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("✗" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.test_connection")
    @patch("builtins.print")
    def test_command(self, mock_print, mock_test):
        """Should successfully run test command."""
        mock_args = MagicMock()
        mock_args.container_ip = "127.0.0.1"
        mock_args.container_name = "birdnet-pi"
        mock_args.port = 4713

        mock_test.return_value = (True, "Connection successful")

        test_command(mock_args)

        mock_test.assert_called_once_with(
            container_ip="127.0.0.1", port=4713, container_name="birdnet-pi"
        )

        # Verify success message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("✓" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.test_connection")
    @patch("builtins.print")
    def test_command__auto_detect_ip(self, mock_print, mock_test, mock_get_ip):
        """Should auto-detect container IP when not provided."""
        mock_args = MagicMock()
        mock_args.container_ip = None
        mock_args.container_name = "test-container"
        mock_args.port = 4713

        mock_get_ip.return_value = "172.18.0.10"
        mock_test.return_value = (True, "Connection successful")

        test_command(mock_args)

        mock_get_ip.assert_called_once_with("test-container")
        mock_test.assert_called_once_with(
            container_ip=None, port=4713, container_name="test-container"
        )

        # Verify auto-detected IP was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("auto-detected IP 172.18.0.10:4713" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.test_connection")
    @patch("builtins.print")
    def test_command__explicit_ip_no_auto_detect(self, mock_print, mock_test):
        """Should not auto-detect when explicit IP is provided."""
        mock_args = MagicMock()
        mock_args.container_ip = "10.0.0.5"
        mock_args.container_name = "test-container"
        mock_args.port = 4713

        mock_test.return_value = (True, "Connection successful")

        with patch(
            "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip"
        ) as mock_get_ip:
            test_command(mock_args)
            mock_get_ip.assert_not_called()  # Should not auto-detect

        # Verify explicit IP was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Testing connection to 10.0.0.5:4713" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.test_connection")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.sys.exit")
    @patch("builtins.print")
    def test_command_failure(self, mock_print, mock_exit, mock_test):
        """Should handle test command failure."""
        mock_args = MagicMock()
        mock_args.container_ip = "127.0.0.1"
        mock_args.container_name = "birdnet-pi"
        mock_args.port = 4713

        mock_test.return_value = (False, "Connection failed")

        test_command(mock_args)

        mock_exit.assert_called_once_with(1)

        # Verify error message and troubleshooting info was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("✗" in call for call in print_calls)
        assert any("Troubleshooting" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_status")
    @patch("builtins.print")
    def test_status_command_basic(self, mock_print, mock_status):
        """Should display status information."""
        mock_args = MagicMock()
        mock_args.json = False

        mock_status.return_value = {
            "macos": True,
            "pulseaudio_installed": True,
            "config_exists": True,
            "cookie_exists": True,
            "server_running": True,
            "config_dir": "/test/config",
            "audio_devices": [{"id": "1", "description": "Test Device"}],
        }

        status_command(mock_args)

        # Verify status information was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("PulseAudio Setup Status" in call for call in print_calls)
        assert any("macOS" in call for call in print_calls)
        assert any("Test Device" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_status")
    @patch("builtins.print")
    def test_status_command__json(self, mock_print, mock_status):
        """Should display status with JSON output."""
        mock_args = MagicMock()
        mock_args.json = True

        status_data = {
            "macos": True,
            "pulseaudio_installed": True,
            "config_exists": True,
            "cookie_exists": True,
            "server_running": True,
            "config_dir": "/test/config",
            "audio_devices": [],
        }
        mock_status.return_value = status_data

        status_command(mock_args)

        # Verify JSON output was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Raw Status (JSON)" in call for call in print_calls)
        # Check that JSON was printed (indented)
        json_printed = False
        for call in print_calls:
            # Look for the actual JSON content by checking for specific patterns
            if '{"macos": true' in call.lower() or '"macos": true' in call.lower():
                json_printed = True
                break
            # Also try to extract and parse actual JSON content
            if "call(" in call and "call_list()" not in call:
                # Extract the content between quotes or parentheses
                try:
                    # Find JSON-like content in the call representation
                    if '"' in call:
                        parts = call.split('"')
                        for part in parts:
                            if part.strip().startswith("{") and part.strip().endswith("}"):
                                json.loads(part.strip())
                                json_printed = True
                                break
                except (json.JSONDecodeError, TypeError, IndexError):
                    continue
                if json_printed:
                    break
        # Less strict check - just verify JSON-like structure was printed
        if not json_printed:
            json_printed = any('"macos"' in call and '"config_dir"' in call for call in print_calls)
        assert json_printed

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_audio_devices")
    @patch("builtins.print")
    def test_devices_command(self, mock_print, mock_devices):
        """Should list available audio devices."""
        mock_args = MagicMock()
        mock_args.json = False

        mock_devices.return_value = [
            {"id": "1", "name": "device1", "description": "Test Microphone 1"},
            {"id": "2", "name": "device2", "description": "Test Microphone 2"},
        ]

        devices_command(mock_args)

        # Verify device information was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Available Audio Input Devices" in call for call in print_calls)
        assert any("Test Microphone 1" in call for call in print_calls)
        assert any("Test Microphone 2" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_audio_devices")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.sys.exit")
    @patch("builtins.print")
    def test_devices_command__no_devices(self, mock_print, mock_exit, mock_devices):
        """Should handle no devices found."""
        mock_args = MagicMock()
        mock_args.json = False

        mock_devices.return_value = []

        devices_command(mock_args)

        mock_exit.assert_called_once_with(1)

        # Verify error message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("No audio devices found" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.cleanup_config")
    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_cleanup_command_confirmed(self, mock_print, mock_input, mock_cleanup):
        """Should clean up configuration when confirmed."""
        mock_args = MagicMock()
        mock_args.force = False

        mock_cleanup.return_value = (True, "Cleanup successful")

        cleanup_command(mock_args)

        mock_cleanup.assert_called_once()

        # Verify success message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("✓" in call for call in print_calls)

    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_cleanup_command_cancelled(self, mock_print, mock_input):
        """Should cancel cleanup when not confirmed."""
        mock_args = MagicMock()
        mock_args.force = False

        cleanup_command(mock_args)

        # Verify cancellation message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("cancelled" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.cleanup_config")
    @patch("builtins.print")
    def test_cleanup_command_forced(self, mock_print, mock_cleanup):
        """Should clean up configuration when forced."""
        mock_args = MagicMock()
        mock_args.force = True

        mock_cleanup.return_value = (True, "Cleanup successful")

        cleanup_command(mock_args)

        mock_cleanup.assert_called_once()

    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.is_macos", return_value=False
    )
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.sys.exit")
    @patch("builtins.print")
    def test_install_command_not_macos(self, mock_print, mock_exit, mock_is_macos):
        """Should fail install command on non-macOS."""
        mock_args = MagicMock()

        install_command(mock_args)

        mock_exit.assert_called_once_with(1)

        # Verify error message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("only supported on macOS" in call for call in print_calls)

    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.is_macos", return_value=True
    )
    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch("builtins.print")
    def test_install_command_already_installed(self, mock_print, mock_installed, mock_is_macos):
        """Should skip install when already installed."""
        mock_args = MagicMock()

        install_command(mock_args)

        # Verify already installed message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("already installed" in call for call in print_calls)

    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.is_macos", return_value=True
    )
    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.is_pulseaudio_installed",
        return_value=False,
    )
    @patch(
        "birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.install_pulseaudio",
        return_value=True,
    )
    @patch("builtins.print")
    def test_install_command(self, mock_print, mock_install, mock_installed, mock_is_macos):
        """Should successfully install PulseAudio."""
        mock_args = MagicMock()

        install_command(mock_args)

        mock_install.assert_called_once()

        # Verify success message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("installed successfully" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main__no_command(self, mock_parser_class):
        """Should print help when no command provided."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse_args.return_value = MagicMock(command=None)

        main()

        mock_parser.print_help.assert_called_once()

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.setup_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_setup_command(self, mock_parser_class, mock_setup_command):
        """Should call setup_command for setup command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="setup")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_setup_command.assert_called_once_with(mock_args)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.test_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_command(self, mock_parser_class, mock_test_command):
        """Should call test_command for test command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="test")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_test_command.assert_called_once_with(mock_args)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.status_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_status_command(self, mock_parser_class, mock_status_command):
        """Should call status_command for status command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="status")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_status_command.assert_called_once_with(mock_args)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.devices_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_devices_command(self, mock_parser_class, mock_devices_command):
        """Should call devices_command for devices command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="devices")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_devices_command.assert_called_once_with(mock_args)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.cleanup_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_cleanup_command(self, mock_parser_class, mock_cleanup_command):
        """Should call cleanup_command for cleanup command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="cleanup")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_cleanup_command.assert_called_once_with(mock_args)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.install_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_install_command(self, mock_parser_class, mock_install_command):
        """Should call install_command for install command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="install")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_install_command.assert_called_once_with(mock_args)

    # Detect IP Command Tests
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip")
    @patch("builtins.print")
    def test_detect_ip_command__running_container(self, mock_print, mock_get_ip):
        """Should display detected IP for running container."""
        mock_args = MagicMock()
        mock_args.container_name = "test-container"
        mock_get_ip.return_value = "172.18.0.11"

        detect_ip_command(mock_args)

        mock_get_ip.assert_called_once_with("test-container")
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Detecting IP for container 'test-container'" in call for call in print_calls)
        assert any("Detected IP: 172.18.0.11" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip")
    @patch("builtins.print")
    def test_detect_ip_command__fallback_ip(self, mock_print, mock_get_ip):
        """Should display fallback IP and helpful message."""
        mock_args = MagicMock()
        mock_args.container_name = "nonexistent-container"
        mock_get_ip.return_value = "127.0.0.1"

        detect_ip_command(mock_args)

        mock_get_ip.assert_called_once_with("nonexistent-container")
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any(
            "Detecting IP for container 'nonexistent-container'" in call for call in print_calls
        )
        assert any("Detected IP: 127.0.0.1" in call for call in print_calls)
        assert any("Note: Fallback IP used" in call for call in print_calls)
        assert any("Container is not running" in call for call in print_calls)
        assert any("Docker is not available" in call for call in print_calls)

    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.PulseAudioSetup.get_container_ip")
    @patch("builtins.print")
    def test_detect_ip_command__default_container_name(self, mock_print, mock_get_ip):
        """Should use default container name when not specified."""
        mock_args = MagicMock()
        mock_args.container_name = "birdnet-pi"
        mock_get_ip.return_value = "172.18.0.12"

        detect_ip_command(mock_args)

        mock_get_ip.assert_called_once_with("birdnet-pi")
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Detecting IP for container 'birdnet-pi'" in call for call in print_calls)

    # Main Command Tests for detect-ip
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.detect_ip_command")
    @patch("birdnetpi.wrappers.pulseaudio_setup_wrapper.argparse.ArgumentParser")
    def test_main_detect_ip_command(self, mock_parser_class, mock_detect_ip_command):
        """Should call detect_ip_command for detect-ip command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_args = MagicMock(command="detect-ip")
        mock_parser.parse_args.return_value = mock_args

        main()

        mock_detect_ip_command.assert_called_once_with(mock_args)
