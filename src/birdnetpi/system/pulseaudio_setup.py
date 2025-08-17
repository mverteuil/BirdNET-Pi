"""PulseAudio setup utility for macOS host to container streaming.

This utility handles the configuration needed to stream audio from a macOS
host to a PulseAudio service running in a Docker container.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Template

from birdnetpi.system.path_resolver import PathResolver


class PulseAudioSetup:
    """Utility for setting up PulseAudio network streaming from macOS to container."""

    @staticmethod
    def is_macos() -> bool:
        """Check if running on macOS."""
        return os.uname().sysname == "Darwin"

    @staticmethod
    def _get_container_ip_direct(container_name: str) -> str | None:
        """Try to get container IP using docker inspect."""
        try:
            result = subprocess.run(
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
            ip = result.stdout.strip()
            if ip and ip != "":
                return ip
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None

    @staticmethod
    def _get_container_ip_from_network(container_name: str) -> str | None:
        """Try to get container IP using docker network inspect."""
        try:
            result = subprocess.run(
                ["docker", "network", "ls", "--format", "json"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Find the network associated with the container
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    network = json.loads(line)
                    if container_name.replace("-", "") in network.get("Name", "").replace("-", ""):
                        ip = PulseAudioSetup._inspect_network_for_container_ip(
                            network["Name"], container_name
                        )
                        if ip:
                            return ip
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return None

    @staticmethod
    def _inspect_network_for_container_ip(network_name: str, container_name: str) -> str | None:
        """Inspect a specific network for container IP."""
        try:
            network_result = subprocess.run(
                ["docker", "inspect", network_name],
                capture_output=True,
                text=True,
                check=True,
            )
            network_data = json.loads(network_result.stdout)[0]
            containers = network_data.get("Containers", {})
            for container_data in containers.values():
                if container_name in container_data.get("Name", ""):
                    ip = container_data.get("IPv4Address", "").split("/")[0]
                    if ip:
                        return ip
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_container_ip(container_name: str = "birdnet-pi") -> str:
        """Get the IP address of a Docker container automatically.

        Args:
            container_name: Name of the Docker container

        Returns:
            Container IP address, or "127.0.0.1" as fallback
        """
        # Try docker inspect first (most reliable for running containers)
        ip = PulseAudioSetup._get_container_ip_direct(container_name)
        if ip:
            return ip

        # Fallback: use docker network inspect
        ip = PulseAudioSetup._get_container_ip_from_network(container_name)
        if ip:
            return ip

        # Container not found or Docker not available - return fallback for local development
        return "127.0.0.1"

    @staticmethod
    def is_pulseaudio_installed() -> bool:
        """Check if PulseAudio is installed (via Homebrew)."""
        try:
            result = subprocess.run(
                ["brew", "list", "pulseaudio"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def install_pulseaudio() -> bool:
        """Install PulseAudio via Homebrew."""
        if not PulseAudioSetup.is_macos():
            raise RuntimeError("PulseAudio installation only supported on macOS")

        try:
            subprocess.run(["brew", "install", "pulseaudio"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def get_pulseaudio_config_dir() -> Path:
        """Get the PulseAudio configuration directory."""
        config_dir = Path.home() / ".config" / "pulse"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    @staticmethod
    def backup_existing_config() -> Path | None:
        """Create a backup of existing PulseAudio configuration."""
        config_dir = PulseAudioSetup.get_pulseaudio_config_dir()
        config_files = ["default.pa", "daemon.conf", "client.conf"]

        backup_files = []
        for config_file in config_files:
            config_path = config_dir / config_file
            if config_path.exists():
                backup_path = config_dir / f"{config_file}.backup"
                try:
                    config_path.rename(backup_path)
                    backup_files.append(backup_path)
                except OSError:
                    continue

        return config_dir if backup_files else None

    @staticmethod
    def create_server_config(
        container_ip: str | None = None,
        port: int = 4713,
        enable_network: bool = True,
        container_name: str = "birdnet-pi",
    ) -> Path:
        """Create PulseAudio server configuration for network streaming."""
        # Auto-detect container IP if not provided
        if container_ip is None:
            container_ip = PulseAudioSetup.get_container_ip(container_name)

        config_dir = PulseAudioSetup.get_pulseaudio_config_dir()

        # Initialize file path resolver
        resolver = PathResolver()

        # Create default.pa configuration
        default_pa_template_path = resolver.get_template_file_path("pulseaudio_default.pa.j2")
        default_pa_template = Template(default_pa_template_path.read_text())
        default_pa_content = default_pa_template.render(
            container_ip=container_ip, port=port, enable_network=enable_network
        )

        default_pa_path = config_dir / "default.pa"
        default_pa_path.write_text(default_pa_content)

        # Create daemon.conf
        daemon_conf_template_path = resolver.get_template_file_path("pulseaudio_daemon.conf.j2")
        daemon_conf_template = Template(daemon_conf_template_path.read_text())
        daemon_conf_content = daemon_conf_template.render()

        daemon_conf_path = config_dir / "daemon.conf"
        daemon_conf_path.write_text(daemon_conf_content)

        return config_dir

    @staticmethod
    def create_auth_cookie() -> Path:
        """Create authentication cookie for PulseAudio."""
        config_dir = PulseAudioSetup.get_pulseaudio_config_dir()
        cookie_path = config_dir / "cookie"

        # Generate random cookie data
        cookie_data = os.urandom(256)
        cookie_path.write_bytes(cookie_data)
        cookie_path.chmod(0o600)

        return cookie_path

    @staticmethod
    def start_pulseaudio_server() -> tuple[bool, str]:
        """Start PulseAudio server in user mode."""
        try:
            # Kill any existing PulseAudio processes
            subprocess.run(["pulseaudio", "-k"], capture_output=True, check=False)

            # Start PulseAudio in daemon mode
            subprocess.run(
                ["pulseaudio", "--start", "-v"],
                capture_output=True,
                text=True,
                check=True,
            )

            return True, "PulseAudio server started successfully"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to start PulseAudio: {e.stderr}"
        except FileNotFoundError:
            return False, "PulseAudio not found in PATH"

    @staticmethod
    def stop_pulseaudio_server() -> tuple[bool, str]:
        """Stop PulseAudio server."""
        try:
            subprocess.run(["pulseaudio", "-k"], capture_output=True, check=True)
            return True, "PulseAudio server stopped successfully"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to stop PulseAudio: {e.stderr}"
        except FileNotFoundError:
            return False, "PulseAudio not found in PATH"

    @staticmethod
    def test_connection(
        container_ip: str | None = None, port: int = 4713, container_name: str = "birdnet-pi"
    ) -> tuple[bool, str]:
        """Test connection to PulseAudio server in container."""
        # Auto-detect container IP if not provided
        if container_ip is None:
            container_ip = PulseAudioSetup.get_container_ip(container_name)

        try:
            # Use pactl to test connection
            env = os.environ.copy()
            env["PULSE_RUNTIME_PATH"] = str(PulseAudioSetup.get_pulseaudio_config_dir())

            result = subprocess.run(
                ["pactl", "-s", f"tcp:{container_ip}:{port}", "info"],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )

            if result.returncode == 0:
                return True, "Successfully connected to container PulseAudio"
            else:
                return False, f"Connection failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Connection timeout - container may not be running"
        except FileNotFoundError:
            return False, "pactl command not found"

    @staticmethod
    def get_audio_devices() -> list[dict[str, str]]:
        """Get list of available audio input devices."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                check=True,
            )

            devices = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        devices.append(
                            {
                                "id": parts[0],
                                "name": parts[1],
                                "description": parts[2] if len(parts) > 2 else parts[1],
                            }
                        )

            return devices
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    @staticmethod
    def setup_streaming(
        container_ip: str | None = None,
        port: int = 4713,
        backup_existing: bool = True,
        container_name: str = "birdnet-pi",
    ) -> tuple[bool, str]:
        """Complete setup for PulseAudio streaming to container."""
        # Auto-detect container IP if not provided
        if container_ip is None:
            container_ip = PulseAudioSetup.get_container_ip(container_name)

        if not PulseAudioSetup.is_macos():
            return False, "This utility only supports macOS"

        if not PulseAudioSetup.is_pulseaudio_installed():
            return False, "PulseAudio not installed. Run: brew install pulseaudio"

        try:
            # Backup existing configuration
            if backup_existing:
                PulseAudioSetup.backup_existing_config()

            # Create server configuration
            config_dir = PulseAudioSetup.create_server_config(
                container_ip, port, container_name=container_name
            )

            # Create authentication cookie
            PulseAudioSetup.create_auth_cookie()

            # Stop any existing server
            PulseAudioSetup.stop_pulseaudio_server()

            # Start server with new configuration
            success, message = PulseAudioSetup.start_pulseaudio_server()
            if not success:
                return False, f"Failed to start server: {message}"

            return (
                True,
                f"PulseAudio setup complete. Config in: {config_dir}\nContainer IP: {container_ip}",
            )

        except Exception as e:
            return False, f"Setup failed: {e!s}"

    @staticmethod
    def cleanup_config() -> tuple[bool, str]:
        """Remove PulseAudio configuration and restore backups."""
        try:
            # Stop server
            PulseAudioSetup.stop_pulseaudio_server()

            config_dir = PulseAudioSetup.get_pulseaudio_config_dir()
            config_files = ["default.pa", "daemon.conf", "client.conf", "cookie"]

            # Remove generated config files
            for config_file in config_files:
                config_path = config_dir / config_file
                if config_path.exists():
                    config_path.unlink()

            # Restore backups
            backup_files = list(config_dir.glob("*.backup"))
            for backup_file in backup_files:
                original_name = backup_file.name.replace(".backup", "")
                original_path = config_dir / original_name
                backup_file.rename(original_path)

            return True, "PulseAudio configuration cleaned up successfully"

        except Exception as e:
            return False, f"Cleanup failed: {e!s}"

    @staticmethod
    def get_status() -> dict[str, Any]:
        """Get current PulseAudio setup status."""
        config_dir = PulseAudioSetup.get_pulseaudio_config_dir()

        status = {
            "macos": PulseAudioSetup.is_macos(),
            "pulseaudio_installed": PulseAudioSetup.is_pulseaudio_installed(),
            "config_dir": str(config_dir),
            "config_exists": (config_dir / "default.pa").exists(),
            "cookie_exists": (config_dir / "cookie").exists(),
            "server_running": False,
            "audio_devices": PulseAudioSetup.get_audio_devices(),
        }

        # Check if server is running
        try:
            result = subprocess.run(
                ["pgrep", "-f", "pulseaudio"],
                capture_output=True,
                check=False,
            )
            status["server_running"] = result.returncode == 0
        except FileNotFoundError:
            pass

        return status
