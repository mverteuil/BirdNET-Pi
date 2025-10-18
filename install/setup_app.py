"""BirdNET-Pi SBC installer with TUI."""

import os
import socket
import subprocess
import sys
from pathlib import Path


def get_ip_address() -> str:
    """Get the primary IP address of this machine.

    Returns:
        str: IP address or 'unknown' if not connected
    """
    try:
        # Create a socket to determine the route to the internet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def install_system_dependencies() -> None:
    """Install system-level dependencies."""
    try:
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        dependencies = [
            # Core dependencies
            "ffmpeg",  # Audio processing
            "sqlite3",  # Database
            "redis-server",  # Cache
            "caddy",  # Web server
            # Audio system
            "alsa-utils",  # Audio drivers
            "pulseaudio",  # Audio server
            "libportaudio2",  # Audio I/O library
            "portaudio19-dev",  # Audio I/O headers (for Python sounddevice)
            # System utilities
            "curl",  # HTTP client
            "ca-certificates",  # SSL certificates
            "systemd-journal-remote",  # Journal access for logs
            # Build dependencies for Python packages
            "libjpeg-dev",  # For Pillow (image processing)
            "zlib1g-dev",  # For various Python packages
        ]
        subprocess.run(
            ["sudo", "apt-get", "install", "-y", "--no-install-recommends", *dependencies],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install system dependencies: {e}")
        sys.exit(1)


def setup_user_and_directories() -> None:
    """Create birdnetpi user and required directories."""
    try:
        # Create user (ignore error if already exists)
        subprocess.run(["sudo", "useradd", "-m", "-s", "/bin/bash", "birdnetpi"], check=False)
        subprocess.run(["sudo", "usermod", "-aG", "audio,video,dialout", "birdnetpi"], check=True)

        # Create directories
        dirs_to_create = [
            "/var/log/birdnetpi",
            "/opt/birdnetpi",
            "/var/lib/birdnetpi/config",
            "/var/lib/birdnetpi/models",
            "/var/lib/birdnetpi/recordings",
            "/var/lib/birdnetpi/database",
        ]
        for d in dirs_to_create:
            subprocess.run(["sudo", "mkdir", "-p", d], check=True)

        subprocess.run(["sudo", "chmod", "777", "/var/log"], check=True)
        subprocess.run(
            [
                "sudo",
                "chown",
                "-R",
                "birdnetpi:birdnetpi",
                "/var/log/birdnetpi",
                "/opt/birdnetpi",
                "/var/lib/birdnetpi",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to create user and directories: {e}")
        sys.exit(1)


def setup_venv_and_dependencies() -> Path:
    """Set up Python virtual environment and install dependencies.

    Returns:
        Path: Path to the virtual environment
    """
    try:
        venv_dir = Path("/opt/birdnetpi/.venv")
        if not venv_dir.exists():
            subprocess.run(
                ["sudo", "-u", "birdnetpi", "python3.11", "-m", "venv", str(venv_dir)],
                check=True,
            )

        # Install uv
        pip_path = str(venv_dir / "bin" / "pip")
        subprocess.run(["sudo", "-u", "birdnetpi", pip_path, "install", "uv"], check=True)

        # Copy project files
        pyproject_path = Path("/opt/birdnetpi/pyproject.toml")
        if not pyproject_path.exists():
            subprocess.run(["sudo", "cp", "pyproject.toml", str(pyproject_path)], check=True)
            subprocess.run(
                ["sudo", "chown", "birdnetpi:birdnetpi", str(pyproject_path)], check=True
            )

        uv_lock_path = Path("/opt/birdnetpi/uv.lock")
        if not uv_lock_path.exists():
            subprocess.run(["sudo", "cp", "uv.lock", str(uv_lock_path)], check=True)
            subprocess.run(["sudo", "chown", "birdnetpi:birdnetpi", str(uv_lock_path)], check=True)

        # Copy source code (required before uv sync can build the package)
        subprocess.run(["sudo", "cp", "-r", "src", "/opt/birdnetpi/"], check=True)
        subprocess.run(
            ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/birdnetpi/src"],
            check=True,
        )

        # Install dependencies with uv
        uv_path = str(venv_dir / "bin" / "uv")
        subprocess.run(
            [
                "sudo",
                "-u",
                "birdnetpi",
                uv_path,
                "sync",
                "--locked",
                "--no-dev",
                f"--python={sys.executable}",
            ],
            cwd="/opt/birdnetpi",
            check=True,
        )

        # Install Rich for installer UI (not in project dependencies)
        pip_path = str(venv_dir / "bin" / "pip")
        subprocess.run(
            ["sudo", "-u", "birdnetpi", pip_path, "install", "rich"],
            check=True,
        )

        return venv_dir

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to set up Python environment: {e}")
        sys.exit(1)


def run_installation_with_progress(venv_path: Path) -> None:
    """Run the main installation with Rich progress UI.

    Args:
        venv_path: Path to the Python virtual environment
    """
    # Import Rich UI (now available after uv sync)
    from ui_progress import InstallStep, ProgressUI

    # Use default configuration for now
    site_name = "BirdNET-Pi"

    ui = ProgressUI()
    ui.show_header(site_name)

    with ui.progress:
        ui.create_tasks()

        # Mark bootstrap steps as complete
        ui.complete_task(InstallStep.SYSTEM_DEPS)
        ui.complete_task(InstallStep.USER_SETUP)
        ui.complete_task(InstallStep.VENV_SETUP)
        ui.complete_task(InstallStep.SOURCE_CODE)
        ui.complete_task(InstallStep.PYTHON_DEPS)

        try:
            # Copy config templates
            ui.update_task(InstallStep.CONFIG_TEMPLATES, advance=20)
            subprocess.run(["sudo", "cp", "-r", "config_templates", "/opt/birdnetpi/"], check=True)
            subprocess.run(
                ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/birdnetpi/config_templates"],
                check=True,
            )

            # Configure Caddy
            caddyfile = Path("/etc/caddy/Caddyfile")
            if not caddyfile.exists():
                subprocess.run(
                    ["sudo", "cp", "config_templates/Caddyfile", str(caddyfile)], check=True
                )
                subprocess.run(["sudo", "chown", "root:root", str(caddyfile)], check=True)
            ui.complete_task(InstallStep.CONFIG_TEMPLATES)

            # Install assets
            ui.update_task(InstallStep.ASSETS, advance=10)
            install_assets_path = venv_path / "bin" / "install-assets"
            result = subprocess.run(
                [
                    "sudo",
                    "-u",
                    "birdnetpi",
                    str(install_assets_path),
                    "install",
                    "v2.2.0",
                    "--include-models",
                    "--include-ioc-db",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                ui.complete_task(InstallStep.ASSETS)
            else:
                ui.show_error("Asset installation failed", result.stderr)

            # Setup systemd services
            ui.update_task(InstallStep.SYSTEMD, advance=10)
            setup_systemd_services(venv_path)
            ui.complete_task(InstallStep.SYSTEMD)

            # Health check
            ui.update_task(InstallStep.HEALTH_CHECK, advance=50)
            ui.complete_task(InstallStep.HEALTH_CHECK)

        except subprocess.CalledProcessError as e:
            ui.show_error(f"Installation failed: {e}")
            sys.exit(1)

    # Show service status and final summary (outside progress context)
    ui.show_service_status()
    ip_address = get_ip_address()
    ui.show_final_summary(ip_address, site_name)


def setup_systemd_services(venv_path: Path) -> None:
    """Set up systemd services for the application.

    Args:
        venv_path: Path to the Python virtual environment
    """
    systemd_dir = "/etc/systemd/system/"
    user = "birdnetpi"
    python_exec = venv_path / "bin" / "python3"
    repo_root = Path("/opt/birdnetpi")

    services = [
        {
            "name": "birdnet_redis.service",
            "description": "Redis Cache Server",
            "after": "network-online.target",
            "exec_start": "/usr/bin/redis-server /opt/birdnetpi/config_templates/redis.conf",
        },
        {
            "name": "birdnet_caddy.service",
            "description": "Caddy Web Server",
            "after": "network-online.target",
            "exec_start": "/usr/bin/caddy run --config /etc/caddy/Caddyfile",
        },
        {
            "name": "birdnet_fastapi.service",
            "description": "BirdNET FastAPI Server",
            "after": "network-online.target birdnet_redis.service",
            "exec_start": (
                f"{python_exec} -m uvicorn birdnetpi.web.main:app --host 0.0.0.0 --port 8888"
            ),
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
        {
            "name": "birdnet_pulseaudio.service",
            "description": "PulseAudio Sound Server",
            "after": "network-online.target",
            "exec_start": "pulseaudio --daemonize=no --exit-idle-time=-1",
        },
        {
            "name": "birdnet_audio_capture.service",
            "description": "BirdNET Audio Capture",
            "after": "network-online.target birdnet_pulseaudio.service",
            "exec_start": f"{venv_path / 'bin' / 'audio-capture-daemon'}",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_capture",
        },
        {
            "name": "birdnet_audio_analysis.service",
            "description": "BirdNET Audio Analysis",
            "after": "network-online.target birdnet_audio_capture.service",
            "exec_start": f"{venv_path / 'bin' / 'audio-analysis-daemon'}",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_analysis",
        },
        {
            "name": "birdnet_audio_websocket.service",
            "description": "BirdNET Audio Websocket",
            "after": "network-online.target birdnet_audio_capture.service",
            "exec_start": f"{venv_path / 'bin' / 'audio-websocket-daemon'}",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_websocket",
        },
        {
            "name": "birdnet_update.service",
            "description": "BirdNET Update Daemon",
            "after": "network-online.target birdnet_fastapi.service",
            "exec_start": f"{venv_path / 'bin' / 'update-daemon'} --mode both",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=update_daemon",
        },
    ]

    for service_config in services:
        service_name = service_config["name"]
        service_file_path = os.path.join(systemd_dir, service_name)
        content = "[Unit]\n"
        content += f"Description={service_config['description']}\n"
        if "after" in service_config:
            content += f"After={service_config['after']}\n"
        content += """
[Service]
Restart=always
Type=simple
"""
        if "environment" in service_config:
            content += f"Environment={service_config['environment']}\n"
        content += f"""User={user}
ExecStart={service_config["exec_start"]}
WorkingDirectory={repo_root}

[Install]
WantedBy=multi-user.target
"""
        temp_file_path = f"/tmp/{service_name}"
        with open(temp_file_path, "w") as f:
            f.write(content)

        subprocess.run(["sudo", "mv", temp_file_path, service_file_path], check=True)
        subprocess.run(["sudo", "systemctl", "enable", service_name], check=True)
        subprocess.run(["sudo", "systemctl", "start", service_name], check=True)

    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)


def main() -> None:
    """Run the main installer."""
    # Check not running as root
    if os.geteuid() == 0:
        print(
            "This script should not be run as root. "
            "Please run as a non-root user with sudo privileges."
        )
        sys.exit(1)

    # Check if we're being re-executed from venv
    in_venv = sys.prefix != sys.base_prefix

    if not in_venv:
        # Phase 1: Bootstrap (no dependencies)
        print("========================================")
        print("BirdNET-Pi SBC Installer")
        print("========================================")
        print()

        print("Installing system dependencies...")
        install_system_dependencies()

        print("Creating user and directories...")
        setup_user_and_directories()

        print("Setting up Python environment...")
        venv_path = setup_venv_and_dependencies()

        # Re-execute this script with venv Python
        print()
        print("Re-executing with virtual environment...")
        venv_python = venv_path / "bin" / "python3"
        os.execv(str(venv_python), [str(venv_python), __file__])
    else:
        # Phase 2: Running from venv, can use Rich now
        venv_path = Path(sys.prefix)
        run_installation_with_progress(venv_path)


if __name__ == "__main__":
    main()
