"""Refactored tests for PulseAudio setup utility using pytest parameterization."""

import json
import os
import subprocess
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
    mock_result = MagicMock(spec=subprocess.CompletedProcess, stdout="172.18.0.2", returncode=0)
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

    @pytest.mark.parametrize(
        "sysname,expected",
        [
            pytest.param("Darwin", True, id="macos"),
            pytest.param("Linux", False, id="linux"),
            pytest.param("Windows", False, id="windows"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.os.uname", autospec=True)
    def test_is_macos(self, mock_uname, sysname, expected):
        """Should correctly detect macOS."""
        mock_uname.return_value = MagicMock(spec=os.uname_result)
        mock_uname.return_value.sysname = sysname
        assert PulseAudioSetup.is_macos() == expected

    @pytest.mark.parametrize(
        "container_name,expected_ip",
        [
            pytest.param("birdnet-pi", "172.18.0.2", id="default-container"),
            pytest.param("custom-container", "172.18.0.2", id="custom-container"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip_success(
        self, mock_run, mock_docker_inspect_success, container_name, expected_ip
    ):
        """Should return container IP when container is running."""
        mock_run.return_value = mock_docker_inspect_success
        result = PulseAudioSetup.get_container_ip(container_name)
        assert result == expected_ip
        mock_run.assert_called_once_with(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    @pytest.mark.parametrize(
        "stdout,expected_ip",
        [
            pytest.param("", "127.0.0.1", id="empty-response"),
            pytest.param("   \n  ", "127.0.0.1", id="whitespace-only"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip_empty_responses(self, mock_run, stdout, expected_ip):
        """Should fallback to 127.0.0.1 for empty responses."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess, stdout=stdout, returncode=0)
        mock_run.return_value = mock_result
        result = PulseAudioSetup.get_container_ip("birdnet-pi")
        assert result == expected_ip

    @pytest.mark.parametrize(
        "side_effect,expected_ip",
        [
            pytest.param(
                subprocess.CalledProcessError(1, "docker"),
                "127.0.0.1",
                id="container-not-found",
            ),
            pytest.param(FileNotFoundError(), "127.0.0.1", id="docker-not-available"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_get_container_ip_errors(self, mock_run, side_effect, expected_ip):
        """Should fallback to 127.0.0.1 on errors."""
        mock_run.side_effect = side_effect
        result = PulseAudioSetup.get_container_ip("test-container")
        assert result == expected_ip

    @pytest.mark.parametrize(
        "returncode,expected_result",
        [
            pytest.param(0, True, id="installed"),
            pytest.param(1, False, id="not-installed"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_is_pulseaudio_installed(self, mock_run, returncode, expected_result):
        """Should detect PulseAudio installation status."""
        mock_run.return_value.returncode = returncode
        assert PulseAudioSetup.is_pulseaudio_installed() == expected_result
        mock_run.assert_called_once_with(
            ["brew", "list", "pulseaudio"], capture_output=True, text=True, check=False
        )

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", side_effect=FileNotFoundError)
    def test_is_pulseaudio_installed_no_brew(self, mock_run):
        """Should return False when brew is not found."""
        assert PulseAudioSetup.is_pulseaudio_installed() is False

    @pytest.mark.parametrize(
        "container_ip,container_name,auto_detect",
        [
            pytest.param("192.168.1.100", None, False, id="explicit-ip"),
            pytest.param(None, "test-container", True, id="auto-detect-custom"),
            pytest.param(None, "birdnet-pi", True, id="auto-detect-default"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True)
    def test_create_server_config_ip_handling(
        self,
        mock_get_ip,
        mock_config_dir,
        repo_root,
        path_resolver,
        container_ip,
        container_name,
        auto_detect,
    ):
        """Should handle IP configuration correctly."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)
        mock_get_ip.return_value = "172.18.0.3"

        with (
            patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
                return_value=mock_config_dir,
            ),
            patch("birdnetpi.system.pulseaudio_setup.Path", autospec=True) as mock_path,
        ):
            mock_file_path = MagicMock(spec=Path)
            mock_path.return_value = mock_file_path
            mock_file_path.parent.parent.parent.parent = repo_root

            if container_ip:
                config_dir = PulseAudioSetup.create_server_config(
                    container_ip=container_ip, port=4713
                )
                mock_get_ip.assert_not_called()
                expected_ip = container_ip
            else:
                config_dir = PulseAudioSetup.create_server_config(
                    container_ip=None, port=4713, container_name=container_name or "birdnet-pi"
                )
                mock_get_ip.assert_called_once_with(container_name or "birdnet-pi")
                expected_ip = "172.18.0.3"

        assert config_dir == mock_config_dir
        default_pa_content = (mock_config_dir / "default.pa").read_text()
        assert expected_ip in default_pa_content

    @pytest.mark.parametrize(
        "container_ip,container_name,use_auto_detect",
        [
            pytest.param("10.0.0.2", None, False, id="explicit-ip-test-connection"),
            pytest.param(None, "test-container", True, id="auto-detect-test-connection"),
            pytest.param(None, None, True, id="default-container-test-connection"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection_ip_handling(self, mock_run, container_ip, container_name, use_auto_detect):
        """Should handle IP configuration in test_connection."""
        mock_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"),
            MagicMock(
                spec=subprocess.CompletedProcess,
                returncode=0,
                stderr="",
                stdout="Server Name: pulseaudio",
            ),
        ]

        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            with patch(
                "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_container_ip", autospec=True
            ) as mock_get_ip:
                mock_get_ip.return_value = "172.18.0.5"

                # Build kwargs with proper types
                if container_ip:
                    success, message = PulseAudioSetup.test_connection(
                        container_ip=container_ip, port=4713
                    )
                elif container_name:
                    success, message = PulseAudioSetup.test_connection(
                        container_name=container_name, port=4713
                    )
                else:
                    success, message = PulseAudioSetup.test_connection(port=4713)

                assert success is True
                assert "successfully connected" in message
                mock_get_ip.assert_not_called()  # Container name is used directly in docker exec

    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_connection_failure(self, mock_run):
        """Should handle connection failure."""
        mock_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="true\n"),
            MagicMock(spec=subprocess.CompletedProcess, returncode=1, stderr="Connection refused"),
        ]
        with patch(
            "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.get_pulseaudio_config_dir",
            return_value=Path("/tmp"),
        ):
            success, message = PulseAudioSetup.test_connection("192.168.1.100", 4713)
        assert success is False
        assert "Connection refused" in message

    @pytest.mark.parametrize(
        "container_ip,container_name,should_auto_detect,expected_ip",
        [
            pytest.param("10.0.0.3", None, False, "10.0.0.3", id="explicit-ip-setup"),
            pytest.param(
                None, "custom-container", True, "172.18.0.7", id="auto-detect-custom-setup"
            ),
            pytest.param(None, None, True, "172.18.0.8", id="auto-detect-default-setup"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.time.sleep", autospec=True)
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos",
        autospec=True,
        return_value=True,
    )
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed",
        autospec=True,
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
    def test_setup_streaming_ip_handling(
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
        container_ip,
        container_name,
        should_auto_detect,
        expected_ip,
    ):
        """Should handle IP configuration in setup_streaming."""
        mock_subprocess.return_value = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stdout="", stderr=""
        )
        mock_config.return_value = tmp_path
        mock_start.return_value = (True, "Started successfully")
        mock_get_ip.return_value = expected_ip

        kwargs = {}
        if container_ip:
            kwargs["container_ip"] = container_ip
        if container_name:
            kwargs["container_name"] = container_name

        success, message = PulseAudioSetup.setup_streaming(**kwargs)

        assert success is True
        if should_auto_detect:
            mock_get_ip.assert_called_once_with(container_name or "birdnet-pi")
            mock_config.assert_called_once_with(
                expected_ip, 4713, container_name=container_name or "birdnet-pi"
            )
            assert expected_ip in message
        else:
            mock_get_ip.assert_not_called()
            mock_config.assert_called_once_with(container_ip, 4713, container_name="birdnet-pi")
            assert container_ip in message

    @pytest.mark.parametrize(
        "is_macos,is_installed,expected_success,expected_message",
        [
            pytest.param(False, True, False, "only supports macOS", id="not-macos"),
            pytest.param(True, False, False, "not installed", id="not-installed"),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_macos", autospec=True)
    @patch(
        "birdnetpi.system.pulseaudio_setup.PulseAudioSetup.is_pulseaudio_installed", autospec=True
    )
    def test_setup_streaming_prerequisites(
        self, mock_installed, mock_macos, is_macos, is_installed, expected_success, expected_message
    ):
        """Should check prerequisites for streaming setup."""
        mock_macos.return_value = is_macos
        mock_installed.return_value = is_installed

        success, message = PulseAudioSetup.setup_streaming()
        assert success == expected_success
        assert expected_message in message

    def test_cleanup_config(self, mock_config_dir):
        """Should clean up configuration files."""
        mock_config_dir.mkdir(parents=True, exist_ok=True)
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
        assert (mock_config_dir / "daemon.conf").exists()


class TestNetworkFallback:
    """Test network fallback scenarios for container IP discovery."""

    @pytest.mark.parametrize(
        "docker_inspect_fails,network_response,inspect_response,expected_ip",
        [
            pytest.param(
                True,
                '{"ID":"abc123","Name":"birdnetpi_network","Driver":"bridge"}\n',
                json.dumps(
                    [
                        {
                            "Name": "birdnetpi_network",
                            "Containers": {
                                "container_id_123": {
                                    "Name": "birdnet-pi",
                                    "IPv4Address": "172.19.0.5/16",
                                }
                            },
                        }
                    ]
                ),
                "172.19.0.5",
                id="successful-fallback",
            ),
            pytest.param(
                True,
                '{"ID":"abc123","Name":"other_network","Driver":"bridge"}',
                None,
                "127.0.0.1",
                id="no-matching-network",
            ),
            pytest.param(
                True,
                "invalid json",
                None,
                "127.0.0.1",
                id="invalid-json",
            ),
            pytest.param(
                True,
                '{"ID":"abc123","Name":"birdnetpi_network","Driver":"bridge"}\n',
                json.dumps([{"Name": "birdnetpi_network", "Containers": {}}]),
                "127.0.0.1",
                id="empty-containers",
            ),
        ],
    )
    @patch("birdnetpi.system.pulseaudio_setup.subprocess.run", autospec=True)
    def test_network_fallback_scenarios(
        self, mock_run, docker_inspect_fails, network_response, inspect_response, expected_ip
    ):
        """Should handle various network fallback scenarios."""
        side_effects = []

        if docker_inspect_fails:
            side_effects.append(subprocess.CalledProcessError(1, "docker"))

        if network_response:
            side_effects.append(
                MagicMock(spec=subprocess.CompletedProcess, stdout=network_response, returncode=0)
            )

        if inspect_response and "birdnetpi_network" in network_response:
            side_effects.append(
                MagicMock(spec=subprocess.CompletedProcess, stdout=inspect_response, returncode=0)
            )

        mock_run.side_effect = side_effects
        result = PulseAudioSetup.get_container_ip("birdnet-pi")
        assert result == expected_ip
