"""Tests for PulseAudio setup utility."""

import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.pulseaudio_setup import PulseAudioSetup


@pytest.fixture
def mock_config_dir(tmp_path):
    """Mock configuration directory."""
    return tmp_path / ".config" / "pulse"


@pytest.fixture
def mock_docker_inspect_success():
    """Mock successful docker inspect response."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.stdout = "172.18.0.2"
    mock_result.returncode = 0
    return mock_result


@pytest.fixture
def mock_docker_network_ls_response():
    """Mock docker network ls response."""
    return (
        '{"ID":"abc123","Name":"birdnetpi_network","Driver":"bridge"}\n'
        '{"ID":"def456","Name":"bridge","Driver":"bridge"}'
    )


@pytest.fixture
def mock_docker_network_inspect_response():
    """Mock docker network inspect response with container data."""
    return json.dumps(
        [
            {
                "Name": "birdnetpi_network",
                "Containers": {
                    "container_id_123": {"Name": "birdnet-pi", "IPv4Address": "172.19.0.5/16"}
                },
            }
        ]
    )


class TestPulseAudioSetup:
    """Test PulseAudioSetup utility methods."""

    @patch("birdnetpi.system.pulseaudio_setup.os.uname", autospec=True)
    def test_is_macos_true(self, mock_uname):
        """Should return True when running on macOS."""
        mock_uname.return_value = MagicMock(spec=os.uname_result)
        mock_uname.return_value.sysname = "Darwin"

        assert PulseAudioSetup.is_macos() is True

    @patch("birdnetpi.system.pulseaudio_setup.os.uname", autospec=True)
    def test_is_macos_false(self, mock_uname):
        """Should return False when not running on macOS."""
        mock_uname.return_value = MagicMock(spec=os.uname_result)
        mock_uname.return_value.sysname = "Linux"

        assert PulseAudioSetup.is_macos() is False

    # Container IP Detection Tests
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__running_container(self, mock_run, mock_docker_inspect_success):
        """Should return container IP when container is running."""
        mock_run.return_value = mock_docker_inspect_success

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "172.18.0.2"
        mock_run.assert_called_once_with(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "birdnet-pi",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__custom_container_name(self, mock_run, mock_docker_inspect_success):
        """Should use custom container name in docker inspect command."""
        mock_run.return_value = mock_docker_inspect_success

        result = PulseAudioSetup.get_container_ip("custom-container")

        assert result == "172.18.0.2"
        mock_run.assert_called_once_with(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "custom-container",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__empty_ip_response(self, mock_run):
        """Should fallback to 127.0.0.1 when docker inspect returns empty IP."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__whitespace_only_response(self, mock_run):
        """Should fallback to 127.0.0.1 when docker inspect returns whitespace."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = "   \n  "
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__container_not_found(self, mock_run):
        """Should fallback to 127.0.0.1 when container is not found."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker")

        result = PulseAudioSetup.get_container_ip("nonexistent-container")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__container_not_running(self, mock_run):
        """Should fallback to 127.0.0.1 when container exists but is not running."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker")

        result = PulseAudioSetup.get_container_ip("stopped-container")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__docker_not_available(self, mock_run):
        """Should fallback to 127.0.0.1 when Docker is not available."""
        mock_run.side_effect = FileNotFoundError()

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__host_networking(self, mock_run):
        """Should fallback to 127.0.0.1 for containers using host networking."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = ""  # Empty IP for host networking
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = PulseAudioSetup.get_container_ip("host-network-container")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_success(
        self, mock_run, mock_docker_network_ls_response, mock_docker_network_inspect_response
    ):
        """Should use network fallback when direct inspect fails but network inspect succeeds."""
        # First call (docker inspect) fails
        # Second call (docker network ls) succeeds
        # Third call (docker inspect network) succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                stdout=mock_docker_network_ls_response,
                spec=subprocess.CompletedProcess,
                returncode=0,
            ),  # network ls
            MagicMock(
                stdout=mock_docker_network_inspect_response,
                spec=subprocess.CompletedProcess,
                returncode=0,
            ),  # network inspect
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "172.19.0.5"
        assert mock_run.call_count == 3

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_no_matching_network(self, mock_run):
        """Should fallback to 127.0.0.1 when network fallback finds no matching network."""
        no_match_network_response = '{"ID":"abc123","Name":"other_network","Driver":"bridge"}'
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                spec=subprocess.CompletedProcess, stdout=no_match_network_response, returncode=0
            ),  # network ls with no match
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_json_decode_error(self, mock_run):
        """Should fallback to 127.0.0.1 when network fallback has JSON decode errors."""
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                spec=subprocess.CompletedProcess, stdout="invalid json", returncode=0
            ),  # network ls with invalid JSON
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_network_inspect_fails(
        self, mock_run, mock_docker_network_ls_response
    ):
        """Should fallback to 127.0.0.1 when network inspect in fallback fails."""
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                stdout=mock_docker_network_ls_response,
                spec=subprocess.CompletedProcess,
                returncode=0,
            ),  # network ls
            subprocess.CalledProcessError(1, "docker"),  # network inspect fails
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_empty_containers(
        self, mock_run, mock_docker_network_ls_response
    ):
        """Should fallback to 127.0.0.1 when network fallback finds network with no containers."""
        empty_network_response = json.dumps([{"Name": "birdnetpi_network", "Containers": {}}])

        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                stdout=mock_docker_network_ls_response,
                spec=subprocess.CompletedProcess,
                returncode=0,
            ),  # network ls
            MagicMock(
                spec=subprocess.CompletedProcess, stdout=empty_network_response, returncode=0
            ),  # network inspect with no containers
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip__network_fallback_container_not_in_network(
        self, mock_run, mock_docker_network_ls_response
    ):
        """Should fallback to 127.0.0.1 when target container is not in the matching network."""
        other_container_response = json.dumps(
            [
                {
                    "Name": "birdnetpi_network",
                    "Containers": {
                        "container_id_123": {
                            "Name": "other-container",
                            "IPv4Address": "172.19.0.5/16",
                        }
                    },
                }
            ]
        )

        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "docker"),  # Direct inspect fails
            MagicMock(
                stdout=mock_docker_network_ls_response,
                spec=subprocess.CompletedProcess,
                returncode=0,
            ),  # network ls
            MagicMock(
                spec=subprocess.CompletedProcess, stdout=other_container_response, returncode=0
            ),  # network inspect with different container
        ]

        result = PulseAudioSetup.get_container_ip("birdnet-pi")

        assert result == "127.0.0.1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
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

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_is_pulseaudio_installed_false(self, mock_run):
        """Should return False when PulseAudio is not installed."""
        mock_run.return_value.returncode = 1

        assert PulseAudioSetup.is_pulseaudio_installed() is False

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", side_effect=FileNotFoundError)
    def test_is_pulseaudio_installed__no_brew(self, mock_run):
        """Should return False when brew is not found."""
        assert PulseAudioSetup.is_pulseaudio_installed() is False

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_install_pulseaudio(self, mock_run, mock_is_macos):
        """Should successfully install PulseAudio."""
        mock_run.return_value.returncode = 0

        result = PulseAudioSetup.install_pulseaudio()

        assert result is True
        mock_run.assert_called_once_with(["brew", "install", "pulseaudio"], check=True)

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=False)
    def test_install_pulseaudio_not_macos(self, mock_is_macos):
        """Should raise error when not on macOS."""
        with pytest.raises(RuntimeError, match="only supported on macOS"):
            PulseAudioSetup.install_pulseaudio()

    @patch("birdnetpi.system.pulseaudio_setup.Path.home", autospec=True)
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
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            result = PulseAudioSetup.backup_existing_config()

        assert result == mock_config_dir
        assert (mock_config_dir / "default.pa.backup").exists()
        assert (mock_config_dir / "daemon.conf.backup").exists()

    def test_backup_existing_config__no_files(self, mock_config_dir):
        """Should return None when no config files exist."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            result = PulseAudioSetup.backup_existing_config()

        assert result is None

    def test_create_server_config(self, mock_config_dir, repo_root, path_resolver):
        """Should create server configuration files."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        # The function calculates templates_dir from __file__, so we need to patch Path
        with (
            patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
                return_value=mock_config_dir,
            ),
            patch("birdnetpi.system.pulseaudio_setup.Path", autospec=True) as mock_path,
        ):
            # Mock the Path(__file__) chain to return our templates directory
            mock_file_path = MagicMock(spec=Path)
            mock_path.return_value = mock_file_path
            mock_file_path.parent.parent.parent.parent = repo_root

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

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    def test_create_server_config__auto_detect_ip(
        self, mock_get_ip, mock_config_dir, repo_root, path_resolver
    ):
        """Should auto-detect container IP when not provided."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)
        mock_get_ip.return_value = "172.18.0.3"

        with (
            patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
                return_value=mock_config_dir,
            ),
            patch("birdnetpi.system.pulseaudio_setup.Path", autospec=True) as mock_path,
        ):
            # Mock the Path(__file__) chain to return our templates directory
            mock_file_path = MagicMock(spec=Path)
            mock_path.return_value = mock_file_path
            mock_file_path.parent.parent.parent.parent = repo_root

            config_dir = PulseAudioSetup.create_server_config(
                container_ip=None,  # Should trigger auto-detection
                port=4713,
                enable_network=True,
                container_name="test-container",
            )

        mock_get_ip.assert_called_once_with("test-container")
        assert config_dir == mock_config_dir

        # Check that auto-detected IP is used
        default_pa_content = (mock_config_dir / "default.pa").read_text()
        assert "172.18.0.3" in default_pa_content

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    def test_create_server_config__auto_detect_default_container(
        self, mock_get_ip, mock_config_dir, repo_root, path_resolver
    ):
        """Should use default container name for auto-detection."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)
        mock_get_ip.return_value = "172.18.0.4"

        with (
            patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
                return_value=mock_config_dir,
            ),
            patch("birdnetpi.system.pulseaudio_setup.Path", autospec=True) as mock_path,
        ):
            # Mock the Path(__file__) chain to return our templates directory
            mock_file_path = MagicMock(spec=Path)
            mock_path.return_value = mock_file_path
            mock_file_path.parent.parent.parent.parent = repo_root

            PulseAudioSetup.create_server_config(container_ip=None)

        mock_get_ip.assert_called_once_with("birdnet-pi")  # Default container name

    def test_create_server_config__explicit_ip_no_auto_detect(
        self, mock_config_dir, repo_root, path_resolver
    ):
        """Should not auto-detect when explicit IP is provided."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
                return_value=mock_config_dir,
            ),
            patch("birdnetpi.system.pulseaudio_setup.Path", autospec=True) as mock_path,
        ):
            # Mock the Path(__file__) chain to return our templates directory
            mock_file_path = MagicMock(spec=Path)
            mock_path.return_value = mock_file_path
            mock_file_path.parent.parent.parent.parent = repo_root

            with patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True
            ) as mock_get_ip:
                PulseAudioSetup.create_server_config(container_ip="10.0.0.1")
                mock_get_ip.assert_not_called()  # Should not auto-detect

        # Check that explicit IP is used
        default_pa_content = (mock_config_dir / "default.pa").read_text()
        assert "10.0.0.1" in default_pa_content

    def test_create_auth_cookie(self, mock_config_dir):
        """Should create authentication cookie."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            cookie_path = PulseAudioSetup.create_auth_cookie()

        expected_path = mock_config_dir / "cookie"
        assert cookie_path == expected_path
        assert cookie_path.exists()
        assert cookie_path.stat().st_size == 256
        assert oct(cookie_path.stat().st_mode)[-3:] == "600"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_start_pulseaudio_server(self, mock_run):
        """Should successfully start PulseAudio server."""
        # Mock pgrep to indicate PulseAudio is NOT running
        pgrep_result = MagicMock(spec=subprocess.CompletedProcess)
        pgrep_result.returncode = 1  # pgrep returns 1 when process not found

        # Mock successful kill and start
        kill_result = MagicMock(spec=subprocess.CompletedProcess)
        kill_result.returncode = 0

        start_result = MagicMock(spec=subprocess.CompletedProcess)
        start_result.returncode = 0
        start_result.stderr = ""

        # Mock verification that PulseAudio is running after start
        verify_result = MagicMock(spec=subprocess.CompletedProcess)
        verify_result.returncode = 0  # pgrep returns 0 when process is found

        mock_run.side_effect = [
            pgrep_result,  # pgrep check - not running
            kill_result,  # pulseaudio -k
            kill_result,  # pkill -x pulseaudio
            start_result,  # pulseaudio --start
            verify_result,  # pgrep verify - now running
        ]

        success, message = PulseAudioSetup.start_pulseaudio_server()

        assert success is True
        assert "started successfully" in message
        assert mock_run.call_count == 5  # pgrep + kill + pkill + start + verify

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_start_pulseaudio_server_failure(self, mock_run):
        """Should handle PulseAudio server start failure."""
        # Mock pgrep to indicate PulseAudio is NOT running
        pgrep_result = MagicMock(spec=subprocess.CompletedProcess)
        pgrep_result.returncode = 1  # pgrep returns 1 when process not found

        # Mock successful kill commands
        kill_result = MagicMock(spec=subprocess.CompletedProcess)
        kill_result.returncode = 0

        # Mock failed start - exception gets caught, then verification shows not running
        start_error = subprocess.CalledProcessError(1, "pulseaudio", stderr="error message")

        # Mock verification that PulseAudio is still NOT running after failed start
        verify_result = MagicMock(spec=subprocess.CompletedProcess)
        verify_result.returncode = 1  # pgrep returns 1 when process not found

        mock_run.side_effect = [
            pgrep_result,  # pgrep check - not running
            kill_result,  # pulseaudio -k
            kill_result,  # pkill -x pulseaudio
            start_error,  # pulseaudio --start fails
            verify_result,  # pgrep verify - still not running
        ]

        success, message = PulseAudioSetup.start_pulseaudio_server()

        assert success is False
        # The error message comes from CalledProcessError
        assert "Failed to start PulseAudio" in message

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_stop_pulseaudio_server(self, mock_run):
        """Should successfully stop PulseAudio server."""
        mock_run.return_value.returncode = 0

        success, message = PulseAudioSetup.stop_pulseaudio_server()

        assert success is True
        assert "stopped successfully" in message

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection(self, mock_run):
        """Should successfully test connection to container."""
        # First call checks container, second tests connection
        mock_run.side_effect = [
            MagicMock(
                spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"
            ),  # Container is running
            MagicMock(
                spec=subprocess.CompletedProcess,
                returncode=0,
                stderr="",
                stdout="Server Name: pulseaudio",
            ),  # Connection succeeds
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection("192.168.1.100", 4713)

        assert success is True
        assert "successfully connected" in message

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection__auto_detect_ip(self, mock_run, mock_get_ip):
        """Should test connection with specified container."""
        # First call checks container, second tests connection
        mock_run.side_effect = [
            MagicMock(
                spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"
            ),  # Container is running
            MagicMock(
                spec=subprocess.CompletedProcess,
                returncode=0,
                stderr="",
                stdout="Server Name: pulseaudio",
            ),  # Connection succeeds
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection(
                container_ip=None, port=4713, container_name="test-container"
            )

        # test_connection doesn't use get_container_ip
        mock_get_ip.assert_not_called()
        assert success is True
        assert "successfully connected" in message

        # Verify docker commands were called correctly
        assert mock_run.call_count == 2
        # First call: docker inspect
        assert "test-container" in mock_run.call_args_list[0][0][0]
        # Second call: docker exec with pactl
        assert "test-container" in mock_run.call_args_list[1][0][0]

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection__auto_detect_default_container(self, mock_run, mock_get_ip):
        """Should use default container name."""
        # First call checks container, second tests connection
        mock_run.side_effect = [
            MagicMock(
                spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"
            ),  # Container is running
            MagicMock(
                spec=subprocess.CompletedProcess,
                returncode=0,
                stderr="",
                stdout="Server Name: pulseaudio",
            ),  # Connection succeeds
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, _message = PulseAudioSetup.test_connection(container_ip=None)

        # Note: test_connection doesn't use container_ip or call get_container_ip
        # It only uses container_name to check if container is running
        assert success is True
        mock_get_ip.assert_not_called()  # test_connection doesn't use get_container_ip

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection__explicit_ip_no_auto_detect(self, mock_run):
        """Should not auto-detect when explicit IP is provided."""
        # Create proper CompletedProcess-like objects using namedtuples
        CompletedProc = namedtuple("CompletedProc", ["returncode", "stdout", "stderr"])

        # First call checks container, second tests connection
        mock_run.side_effect = [
            CompletedProc(returncode=0, stdout="true\n", stderr=""),  # Container is running
            CompletedProc(returncode=0, stdout="", stderr=""),  # Connection succeeds
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            with patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True
            ) as mock_get_ip:
                PulseAudioSetup.test_connection(container_ip="10.0.0.2")
                mock_get_ip.assert_not_called()  # Should not auto-detect

        # Verify docker exec was called (second call)
        assert mock_run.call_count == 2
        args = mock_run.call_args_list[1][0][0]  # Second call arguments
        assert "docker" in args
        assert "exec" in args
        assert "pactl" in args
        # Note: container_ip parameter is not used by test_connection

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection_failure(self, mock_run):
        """Should handle connection failure."""
        # First call checks if container is running (docker inspect)
        # Second call tests the connection (pactl)
        mock_run.side_effect = [
            MagicMock(
                spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"
            ),  # Container is running
            MagicMock(
                spec=subprocess.CompletedProcess, returncode=1, stderr="Connection refused"
            ),  # Connection fails
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection("192.168.1.100", 4713)

        assert success is False
        assert "Connection refused" in message

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_audio_devices(self, mock_run):
        """Should return list of audio devices."""
        mock_run.return_value.stdout = "0\tdevice1\tMicrophone 1\n1\tdevice2\tMicrophone 2"
        mock_run.return_value.returncode = 0

        devices = PulseAudioSetup.get_audio_devices()

        assert len(devices) == 2
        assert devices[0]["id"] == "0"
        assert devices[0]["name"] == "device1"
        assert devices[0]["description"] == "Microphone 1"

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", side_effect=FileNotFoundError)
    def test_get_audio_devices__no_pactl(self, mock_run):
        """Should return empty list when pactl is not available."""
        devices = PulseAudioSetup.get_audio_devices()
        assert devices == []

    @patch(
        "birdnetpi.system.pulseaudio_setup.time.sleep", autospec=True
    )  # Mock sleep to prevent slowness
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)  # Mock subprocess
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.backup_existing_config", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_server_config", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_auth_cookie", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server", autospec=True
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.start_pulseaudio_server", autospec=True
    )
    def test_setup_streaming(
        self,
        mock_start,
        mock_stop,
        mock_cookie,
        mock_config,
        mock_backup,
        mock_installed,
        mock_macos,
        mock_subprocess,
        mock_sleep,
        tmp_path,
    ):
        """Should successfully setup streaming."""
        # Mock brew services check to avoid real subprocess call
        mock_subprocess.return_value = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr=""
        )

        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")

        success, message = PulseAudioSetup.setup_streaming()

        assert success is True
        assert str(tmp_path) in message
        mock_backup.assert_called_once()
        mock_config.assert_called_once()
        mock_cookie.assert_called_once()
        # Verify sleep was not actually called (mocked)
        mock_sleep.assert_not_called()  # No brew services so no sleep needed

    @patch(
        "birdnetpi.system.pulseaudio_setup.time.sleep", autospec=True
    )  # Mock sleep to prevent slowness
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)  # Mock subprocess
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.backup_existing_config", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_server_config", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_auth_cookie", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server", autospec=True
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.start_pulseaudio_server", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    def test_setup_streaming__auto_detect_ip(
        self,
        mock_get_ip,
        mock_start,
        mock_stop,
        mock_cookie,
        mock_config,
        mock_backup,
        mock_installed,
        mock_macos,
        mock_subprocess,
        mock_sleep,
        tmp_path,
    ):
        """Should auto-detect container IP when not provided."""
        # Mock brew services check to avoid real subprocess call
        mock_subprocess.return_value = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr=""
        )

        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")
        mock_get_ip.return_value = "172.18.0.7"

        success, message = PulseAudioSetup.setup_streaming(
            container_ip=None, container_name="custom-container"
        )

        assert success is True
        mock_get_ip.assert_called_once_with("custom-container")
        mock_config.assert_called_once_with("172.18.0.7", 4713, container_name="custom-container")
        assert "172.18.0.7" in message
        mock_sleep.assert_not_called()  # No brew services so no sleep needed

    @patch(
        "birdnetpi.system.pulseaudio_setup.time.sleep", autospec=True
    )  # Mock sleep to prevent slowness
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)  # Mock subprocess
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.backup_existing_config", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_server_config", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_auth_cookie", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server", autospec=True
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.start_pulseaudio_server", autospec=True
    )
    def test_setup_streaming__explicit_ip_no_auto_detect(
        self,
        mock_start,
        mock_stop,
        mock_cookie,
        mock_config,
        mock_backup,
        mock_installed,
        mock_macos,
        mock_subprocess,
        mock_sleep,
        tmp_path,
    ):
        """Should not auto-detect when explicit IP is provided."""
        # Mock brew services check to avoid real subprocess call
        mock_subprocess.return_value = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr=""
        )

        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True
        ) as mock_get_ip:
            success, message = PulseAudioSetup.setup_streaming(container_ip="10.0.0.3")
            mock_get_ip.assert_not_called()  # Should not auto-detect

        assert success is True
        mock_config.assert_called_once_with("10.0.0.3", 4713, container_name="birdnet-pi")
        assert "10.0.0.3" in message
        mock_sleep.assert_not_called()  # No brew services so no sleep needed

    @patch(
        "birdnetpi.system.pulseaudio_setup.time.sleep", autospec=True
    )  # Mock sleep to prevent slowness
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)  # Mock subprocess
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.backup_existing_config", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_server_config", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.create_auth_cookie", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server", autospec=True
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.start_pulseaudio_server", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    def test_setup_streaming__auto_detect_default_container(
        self,
        mock_get_ip,
        mock_start,
        mock_stop,
        mock_cookie,
        mock_config,
        mock_backup,
        mock_installed,
        mock_macos,
        mock_subprocess,
        mock_sleep,
        tmp_path,
    ):
        """Should use default container name for auto-detection."""
        # Mock brew services check to avoid real subprocess call
        mock_subprocess.return_value = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr=""
        )

        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")
        mock_get_ip.return_value = "172.18.0.8"

        PulseAudioSetup.setup_streaming(container_ip=None)

        mock_get_ip.assert_called_once_with("birdnet-pi")  # Default container name
        mock_sleep.assert_not_called()  # No brew services so no sleep needed

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=False)
    def test_setup_streaming_not_macos(self, mock_macos):
        """Should fail when not on macOS."""
        success, message = PulseAudioSetup.setup_streaming()

        assert success is False
        assert "only supports macOS" in message

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
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
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=mock_config_dir,
        ):
            with patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.stop_pulseaudio_server",
                return_value=(True, "Stopped"),
            ):
                success, message = PulseAudioSetup.cleanup_config()

        assert success is True
        assert "cleaned up successfully" in message
        assert not (mock_config_dir / "default.pa").exists()
        assert not (mock_config_dir / "cookie").exists()
        assert (mock_config_dir / "daemon.conf").exists()  # Restored from backup

    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", return_value=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir", autospec=True
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_audio_devices", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
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
