"""BirdNET-Pi SBC installer with parallel execution."""

import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Thread-safe logging
_log_lock = threading.Lock()


def log(status: str, message: str) -> None:
    """Thread-safe logging with timestamp.

    Args:
        status: Status symbol (arrow, check, x, info)
        message: Message to log
    """
    with _log_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {status} {message}", flush=True)


def run_parallel(tasks: list[tuple[str, Callable[[], None]]]) -> None:
    """Run tasks in parallel and wait for all to complete.

    Args:
        tasks: List of (description, function) tuples
    """
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {}

        # Submit all tasks
        for name, func in tasks:
            log("→", name)
            future = executor.submit(func)
            futures[future] = name

        # Wait for completion
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
                log("✓", name)
            except Exception as e:
                log("✗", f"{name}: {e}")
                raise


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


def apt_update() -> None:
    """Update package lists."""
    subprocess.run(
        ["sudo", "apt-get", "update"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_system_packages() -> None:
    """Install system-level package dependencies."""
    dependencies = [
        # ONLY packages NOT in Raspberry Pi OS Lite by default
        "redis-server",  # Cache server - NOT in Lite
        "caddy",  # Web server/reverse proxy - NOT in Lite
        "portaudio19-dev",  # Audio I/O headers for building sounddevice
    ]
    # Already in Raspberry Pi OS Lite (verified 2024-07-04 Bookworm):
    # - curl, ca-certificates, alsa-utils
    # - sqlite3, libsqlite3-0
    # - libportaudio2, libportaudiocpp0 (PortAudio runtime libraries)
    # - libjpeg-dev (as libjpeg62-turbo-dev), zlib1g-dev
    # Note: We use ALSA directly via PortAudio, no PulseAudio daemon needed
    subprocess.run(
        ["sudo", "apt-get", "install", "-y", "--no-install-recommends", *dependencies],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def create_user_and_directories() -> None:
    """Create birdnetpi user and required directories."""
    # Create user (ignore error if already exists)
    subprocess.run(
        ["sudo", "useradd", "-m", "-s", "/bin/bash", "birdnetpi"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "usermod", "-aG", "audio,video,dialout", "birdnetpi"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
        subprocess.run(
            ["sudo", "mkdir", "-p", d],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    subprocess.run(
        ["sudo", "chmod", "777", "/var/log"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def create_venv() -> None:
    """Create Python virtual environment."""
    venv_dir = Path("/opt/birdnetpi/.venv")
    if not venv_dir.exists():
        subprocess.run(
            ["sudo", "-u", "birdnetpi", "python3.11", "-m", "venv", str(venv_dir)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def install_uv() -> None:
    """Install uv package manager into venv."""
    pip_path = "/opt/birdnetpi/.venv/bin/pip"
    subprocess.run(
        ["sudo", "-u", "birdnetpi", pip_path, "install", "-q", "uv"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def copy_project_files() -> None:
    """Copy pyproject.toml and uv.lock to installation directory."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    for filename in ["pyproject.toml", "uv.lock"]:
        dest_path = Path(f"/opt/birdnetpi/{filename}")
        if not dest_path.exists():
            subprocess.run(
                ["sudo", "cp", str(repo_root / filename), str(dest_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["sudo", "chown", "birdnetpi:birdnetpi", str(dest_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def copy_source_code() -> None:
    """Copy source code to installation directory."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    subprocess.run(
        ["sudo", "cp", "-r", str(repo_root / "src"), "/opt/birdnetpi/"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/birdnetpi/src"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_python_dependencies() -> None:
    """Install Python dependencies with uv."""
    uv_path = "/opt/birdnetpi/.venv/bin/uv"
    subprocess.run(
        [
            "sudo",
            "-u",
            "birdnetpi",
            uv_path,
            "sync",
            "--locked",
            "--no-dev",
            "--quiet",
            f"--python={sys.executable}",
        ],
        cwd="/opt/birdnetpi",
        check=True,
    )


def install_assets() -> None:
    """Download and install BirdNET assets."""
    install_assets_path = "/opt/birdnetpi/.venv/bin/install-assets"
    result = subprocess.run(
        [
            "sudo",
            "-u",
            "birdnetpi",
            install_assets_path,
            "install",
            "latest",
            "--skip-existing",
        ],
        env={**os.environ, "BIRDNETPI_DATA": "/var/lib/birdnetpi"},
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Asset installation failed: {result.stderr}")


def copy_config_templates() -> None:
    """Copy configuration templates to installation directory."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    subprocess.run(
        ["sudo", "cp", "-r", str(repo_root / "config_templates"), "/opt/birdnetpi/"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/birdnetpi/config_templates"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def configure_caddy() -> None:
    """Configure Caddy web server for port 80."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    caddyfile = Path("/etc/caddy/Caddyfile")
    caddyfile_backup = Path("/etc/caddy/Caddyfile.original")

    # Backup original Caddyfile if it exists and hasn't been backed up yet
    if caddyfile.exists() and not caddyfile_backup.exists():
        subprocess.run(
            ["sudo", "cp", str(caddyfile), str(caddyfile_backup)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Copy template first, then replace :8000 with :80 in place for SBC installs
    subprocess.run(
        ["sudo", "cp", str(repo_root / "config_templates" / "Caddyfile"), str(caddyfile)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "sed", "-i", "s/:8000/:80/g", str(caddyfile)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "root:root", str(caddyfile)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Reload Caddy to pick up new configuration (if already running)
    subprocess.run(
        ["sudo", "systemctl", "reload-or-restart", "caddy"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def setup_systemd_services() -> None:
    """Set up systemd services for the application."""
    systemd_dir = "/etc/systemd/system/"
    user = "birdnetpi"
    python_exec = "/opt/birdnetpi/.venv/bin/python3"
    repo_root = "/opt/birdnetpi"

    # Enable and start system services (Redis, Caddy)
    # Note: No PulseAudio daemon on Raspberry Pi OS Lite - we use ALSA directly via PortAudio
    system_services = ["redis-server", "caddy"]
    for service in system_services:
        subprocess.run(
            ["sudo", "systemctl", "enable", service],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "start", service],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    services = [
        {
            "name": "birdnetpi-fastapi.service",
            "description": "BirdNET FastAPI Server",
            "after": "network-online.target redis-server.service",
            "exec_start": (
                f"{python_exec} -m uvicorn birdnetpi.web.main:app --host 127.0.0.1 --port 8888"
            ),
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
        {
            "name": "birdnetpi-audio-capture.service",
            "description": "BirdNET Audio Capture",
            "after": "network-online.target",
            "exec_start": "/opt/birdnetpi/.venv/bin/audio-capture-daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_capture",
        },
        {
            "name": "birdnetpi-audio-analysis.service",
            "description": "BirdNET Audio Analysis",
            "after": "network-online.target birdnetpi-audio-capture.service",
            "exec_start": "/opt/birdnetpi/.venv/bin/audio-analysis-daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_analysis",
        },
        {
            "name": "birdnetpi-audio-websocket.service",
            "description": "BirdNET Audio Websocket",
            "after": "network-online.target birdnetpi-audio-capture.service",
            "exec_start": "/opt/birdnetpi/.venv/bin/audio-websocket-daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=audio_websocket",
        },
        {
            "name": "birdnetpi-update.service",
            "description": "BirdNET Update Monitor",
            "after": "network-online.target birdnetpi-fastapi.service",
            "exec_start": "/opt/birdnetpi/.venv/bin/update-daemon --mode both",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=update_daemon",
        },
        {
            "name": "birdnetpi-epaper-display.service",
            "description": "BirdNET E-Paper Display",
            "after": "network-online.target birdnetpi-fastapi.service",
            "exec_start": "/opt/birdnetpi/.venv/bin/epaper-display-daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src SERVICE_NAME=epaper_display",
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

        subprocess.run(
            ["sudo", "mv", temp_file_path, service_file_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "enable", service_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "start", service_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    subprocess.run(
        ["sudo", "systemctl", "daemon-reload"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def check_service_status(service_name: str) -> str:
    """Check systemd service status.

    Args:
        service_name: Name of the systemd service

    Returns:
        str: Status symbol (✓, ✗, or ○)
    """
    result = subprocess.run(
        ["systemctl", "is-active", service_name],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout.strip() == "active":
        return "✓"
    elif result.returncode == 3:  # Service not loaded
        return "○"
    else:
        return "✗"


def show_final_summary(ip_address: str) -> None:
    """Show installation completion summary.

    Args:
        ip_address: IP address of the installed system
    """
    print()
    print("=" * 60)
    print("Installation Complete!")
    print("=" * 60)
    print()

    # Show service status
    services = [
        "redis-server.service",
        "caddy.service",
        "birdnetpi-fastapi.service",
        "birdnetpi-audio-capture.service",
        "birdnetpi-audio-analysis.service",
        "birdnetpi-audio-websocket.service",
        "birdnetpi-update.service",
    ]

    print("Service Status:")
    for service in services:
        status = check_service_status(service)
        print(f"  {status} {service}")

    print()
    print(f"Web Interface: http://{ip_address}")
    print(f"SSH Access: ssh birdnetpi@{ip_address}")
    print()
    print("The system is now capturing and analyzing bird calls.")
    print("Visit the web interface to view detections and configure settings.")
    print()
    print("=" * 60)


def main() -> None:
    """Run the main installer with parallel execution."""
    # Check not running as root
    if os.geteuid() == 0:
        print("ERROR: This script should not be run as root.")
        print("Please run as a non-root user with sudo privileges.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("BirdNET-Pi SBC Installer")
    print("=" * 60)
    print()

    try:
        # Wave 1: Foundation (sequential)
        log("→", "Creating user and directories")
        create_user_and_directories()
        log("✓", "Creating user and directories")

        log("→", "Updating package lists")
        apt_update()
        log("✓", "Updating package lists")

        # Wave 2: System packages and venv (parallel)
        run_parallel(
            [
                ("Installing system packages", install_system_packages),
                ("Creating Python virtual environment", create_venv),
            ]
        )

        # Wave 3: Venv setup (parallel - after venv exists)
        run_parallel(
            [
                ("Installing uv package manager", install_uv),
                ("Copying project files", copy_project_files),
            ]
        )

        # Wave 4: Source code installation (sequential - uv needs source)
        log("→", "Copying source code")
        copy_source_code()
        log("✓", "Copying source code")

        log("→", "Installing Python dependencies")
        install_python_dependencies()
        log("✓", "Installing Python dependencies")

        # Wave 5: Assets and configuration (parallel)
        run_parallel(
            [
                ("Downloading BirdNET assets", install_assets),
                ("Copying configuration templates", copy_config_templates),
                ("Configuring Caddy web server", configure_caddy),
            ]
        )

        # Wave 6: Services and final checks (sequential)
        log("→", "Setting up systemd services")
        setup_systemd_services()
        log("✓", "Setting up systemd services")

        # Show final summary
        ip_address = get_ip_address()
        show_final_summary(ip_address)

    except Exception as e:
        log("✗", f"Installation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
