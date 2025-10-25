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
from typing import TypedDict

from jinja2 import Template


class DeviceSpecs(TypedDict):
    """Device specifications returned by detect_device_specs()."""

    device_type: str
    total_ram_mb: int
    maxmemory: str
    memory_comment: str


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


def detect_device_specs() -> DeviceSpecs:
    """Detect device type and memory specifications.

    Returns:
        DeviceSpecs: Device specifications including:
            - device_type: Detected device name or 'Unknown' (str)
            - total_ram_mb: Total RAM in MB (int)
            - maxmemory: Redis memory limit (e.g., '32mb', '64mb', '128mb') (str)
            - memory_comment: Explanation for the memory limit (str)
    """
    # Get total RAM
    try:
        meminfo = Path("/proc/meminfo").read_text()
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
                total_mb = total_kb // 1024
                break
        else:
            total_mb = 512  # Default fallback
    except Exception:
        total_mb = 512  # Default fallback

    # Detect device type
    device_type = "Unknown"
    try:
        model_info = Path("/proc/device-tree/model").read_text().strip("\x00")
        device_type = model_info
    except Exception:
        pass

    # Determine Redis memory limits based on total RAM
    # Leave sufficient room for:
    # - System (kernel, system services): ~100-150MB
    # - Python daemons (audio/analysis/web): ~150-200MB
    # - Buffer for peaks and filesystem cache: ~100MB
    if total_mb <= 512:
        # Pi Zero 2W or similar: 512MB total
        # Very tight - minimal Redis, consider display-only mode
        maxmemory = "32mb"
        memory_comment = "Minimal limit for 512MB devices (display-only recommended)"
    elif total_mb <= 1024:
        # Pi 3B or similar: 1GB total
        maxmemory = "64mb"
        memory_comment = "Conservative limit for 1GB devices"
    elif total_mb <= 2048:
        # Pi 4B 2GB
        maxmemory = "128mb"
        memory_comment = "Moderate limit for 2GB devices"
    else:
        # Pi 4B 4GB+ or Pi 5
        maxmemory = "256mb"
        memory_comment = "Standard limit for 4GB+ devices"

    return {
        "device_type": device_type,
        "total_ram_mb": total_mb,
        "maxmemory": maxmemory,
        "memory_comment": memory_comment,
    }


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
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def create_directories() -> None:
    """Create required data directories.

    Note: /opt/birdnetpi and birdnetpi user are created by install.sh before cloning.
    """
    # Create data directories
    dirs_to_create = [
        "/var/log/birdnetpi",
        "/var/lib/birdnetpi/config",
        "/var/lib/birdnetpi/models",
        "/var/lib/birdnetpi/recordings",
        "/var/lib/birdnetpi/database",
    ]
    for d in dirs_to_create:
        subprocess.run(
            ["sudo", "mkdir", "-p", d],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    subprocess.run(
        ["sudo", "chmod", "777", "/var/log"],
        check=True,
        stdin=subprocess.DEVNULL,
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
            "/var/lib/birdnetpi",
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_uv() -> None:
    """Install uv package manager using official installer.

    Uses the standalone installer which doesn't require pip.
    Installs to /opt/uv for consistency across installations.
    UV will automatically create and manage the virtual environment
    when we run 'uv sync' later.
    """
    import pwd

    # Get birdnetpi user's home directory
    birdnetpi_home = pwd.getpwnam("birdnetpi").pw_dir

    # Create /opt/uv directory
    subprocess.run(
        ["sudo", "mkdir", "-p", "/opt/uv"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/uv"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Download and run the official uv installer
    # The installer installs to $HOME/.local/bin by default
    result = subprocess.run(
        [
            "sudo",
            "-u",
            "birdnetpi",
            "sh",
            "-c",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to install uv: {result.stderr}")

    # Move uv binary to /opt/uv/bin for consistency
    subprocess.run(
        ["sudo", "mkdir", "-p", "/opt/uv/bin"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    uv_source = f"{birdnetpi_home}/.local/bin/uv"
    subprocess.run(
        ["sudo", "mv", uv_source, "/opt/uv/bin/uv"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/uv"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def enable_spi_interface() -> bool:
    """Enable SPI interface in Raspberry Pi boot configuration.

    Waveshare e-paper HATs require SPI to be enabled. This function checks if
    SPI is enabled and enables it if needed.

    Returns:
        bool: True if a reboot is required to apply changes
    """
    boot_config = Path("/boot/firmware/config.txt")
    if not boot_config.exists():
        # Not a Raspberry Pi or config not found
        return False

    try:
        content = boot_config.read_text()

        # Check if SPI is already enabled (uncommented dtparam=spi=on exists)
        lines = content.split("\n")
        spi_enabled = any(line.strip() == "dtparam=spi=on" for line in lines)

        if spi_enabled:
            return False  # Already enabled, no reboot needed

        # Enable SPI by uncommenting the line
        updated_content = content.replace("#dtparam=spi=on", "dtparam=spi=on")

        # If the line doesn't exist at all, add it
        if "dtparam=spi=on" not in updated_content:
            updated_content += "\n# Enable SPI for e-paper HAT\ndtparam=spi=on\n"

        # Write the updated config
        subprocess.run(
            ["sudo", "tee", str(boot_config)],
            input=updated_content,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        log("✓", "SPI interface enabled in boot config (reboot required)")
        return True  # Reboot required

    except Exception as e:
        log("✗", f"Failed to enable SPI: {e}")
        return False


def has_waveshare_epaper_hat() -> bool:
    """Detect if a Waveshare e-paper HAT is connected.

    Waveshare e-paper HATs use SPI interface. We detect them by checking for
    SPI devices at /dev/spidev*.

    Returns:
        bool: True if SPI devices are detected (indicating potential e-paper HAT)
    """
    try:
        # Check if /dev/spidev0.0 or /dev/spidev0.1 exists
        spi_devices = list(Path("/dev").glob("spidev*"))
        return len(spi_devices) > 0
    except Exception:
        return False


def install_python_dependencies() -> None:
    """Install Python dependencies with uv.

    UV will automatically create the virtual environment at .venv/
    during the sync operation. If a Waveshare e-paper HAT is detected,
    the epaper extras will be installed automatically.
    """
    # Build uv sync command
    cmd = [
        "sudo",
        "-u",
        "birdnetpi",
        "/opt/uv/bin/uv",
        "sync",
        "--locked",
        "--no-dev",
        "--quiet",
    ]

    # Auto-detect and install e-paper dependencies if hardware is present
    if has_waveshare_epaper_hat():
        log("ℹ", "Waveshare e-paper HAT detected (SPI devices found)")  # noqa: RUF001
        cmd.extend(["--extra", "epaper"])
    else:
        log("ℹ", "No e-paper HAT detected, skipping epaper extras")  # noqa: RUF001

    # Retry up to 3 times for network failures (GitHub access for waveshare-epd)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(
            cmd,
            cwd="/opt/birdnetpi",
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            break

        # Check if it's a network error
        if "Could not resolve host" in result.stderr or "failed to fetch" in result.stderr:
            if attempt < max_retries:
                log("⚠", f"Network error, retrying ({attempt}/{max_retries})...")
                import time

                time.sleep(5)  # Wait 5 seconds before retry
                continue

        # Non-network error or final retry failed
        raise RuntimeError(f"Failed to install Python dependencies: {result.stderr}")


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


def configure_redis() -> None:
    """Configure Redis with memory limits optimized for device specs."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    redis_conf = "/etc/redis/redis.conf"
    redis_conf_backup = "/etc/redis/redis.conf.original"

    # Backup original redis.conf if it exists and hasn't been backed up yet
    # Use test -f to check file existence with sudo permissions
    backup_check = subprocess.run(
        ["sudo", "test", "-f", redis_conf_backup],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if backup_check.returncode != 0:  # Backup doesn't exist
        subprocess.run(
            ["sudo", "cp", "-n", redis_conf, redis_conf_backup],
            check=False,  # Don't fail if source doesn't exist
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Detect device specifications
    device_specs = detect_device_specs()
    log(
        "ℹ",  # noqa: RUF001
        f"Detected: {device_specs['device_type']} ({device_specs['total_ram_mb']}MB RAM)",
    )
    log("ℹ", f"Redis memory limit: {device_specs['maxmemory']}")  # noqa: RUF001

    # Render Redis configuration from template
    template_path = repo_root / "config_templates" / "redis.conf.j2"
    template_content = template_path.read_text()
    template = Template(template_content)
    rendered_config = template.render(**device_specs)

    # Write rendered configuration to temporary file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as tmp:
        tmp.write(rendered_config)
        tmp_path = tmp.name

    try:
        # Copy rendered config to system location
        subprocess.run(
            ["sudo", "cp", tmp_path, redis_conf],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "chown", "redis:redis", redis_conf],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        # Clean up temporary file
        Path(tmp_path).unlink(missing_ok=True)


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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Copy template first, then replace :8000 with :80 in place for SBC installs
    subprocess.run(
        ["sudo", "cp", str(repo_root / "config_templates" / "Caddyfile"), str(caddyfile)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "sed", "-i", "s/:8000/:80/g", str(caddyfile)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "chown", "root:root", str(caddyfile)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Reload Caddy to pick up new configuration (if already running)
    subprocess.run(
        ["sudo", "systemctl", "reload-or-restart", "caddy"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def disable_unnecessary_services(total_ram_mb: int) -> None:
    """Disable unnecessary system services and swap on low-memory devices.

    Args:
        total_ram_mb: Total RAM in MB from device detection
    """
    # Only disable services on very low-memory devices (512MB or less)
    if total_ram_mb > 512:
        return

    # Services safe to disable on headless Pi Zero 2W
    # Saves ~12MB RAM total
    services_to_disable = [
        "ModemManager",  # ~3.3MB - cellular modem support not needed
        "bluetooth",  # ~1.9MB - Bluetooth not needed for BirdNET-Pi
        "triggerhappy",  # ~1.6MB - hotkey daemon not needed headless
        "avahi-daemon",  # ~2.8MB - mDNS/Bonjour nice-to-have but not essential
    ]

    log(
        "ℹ",  # noqa: RUF001
        f"Low memory detected ({total_ram_mb}MB) - optimizing system",
    )

    # Disable swap to prevent SD card wear and thrashing
    try:
        subprocess.run(
            ["sudo", "dphys-swapfile", "swapoff"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "dphys-swapfile", "uninstall"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "disable", "dphys-swapfile"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("✓", "Disabled swap (prevents SD card wear)")
    except Exception as e:
        log("⚠", f"Could not disable swap: {e}")

    for service in services_to_disable:
        try:
            # Check if service exists before trying to disable
            result = subprocess.run(
                ["systemctl", "is-enabled", service],
                check=False,
                capture_output=True,
                text=True,
            )
            # Only disable if service exists and is enabled
            if result.returncode == 0:
                subprocess.run(
                    ["sudo", "systemctl", "disable", "--now", service],
                    check=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log("✓", f"Disabled {service}")
        except Exception as e:
            # Don't fail installation if we can't disable a service
            log("⚠", f"Could not disable {service}: {e}")


def install_systemd_services() -> None:
    """Install and enable systemd services without starting them."""
    systemd_dir = "/etc/systemd/system/"
    user = "birdnetpi"
    python_exec = "/opt/birdnetpi/.venv/bin/python3"
    repo_root = "/opt/birdnetpi"

    # Enable system services (Redis, Caddy) but don't start yet
    # Note: No PulseAudio daemon on Raspberry Pi OS Lite - we use ALSA directly via PortAudio
    system_services = ["redis-server", "caddy"]
    for service in system_services:
        subprocess.run(
            ["sudo", "systemctl", "enable", service],
            check=True,
            stdin=subprocess.DEVNULL,
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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "enable", service_name],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    subprocess.run(
        ["sudo", "systemctl", "daemon-reload"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_systemd_services() -> None:
    """Start all systemd services."""
    # Start system services first
    system_services = ["redis-server", "caddy"]
    for service in system_services:
        subprocess.run(
            ["sudo", "systemctl", "start", service],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Start BirdNET services
    birdnet_services = [
        "birdnetpi-fastapi.service",
        "birdnetpi-audio-capture.service",
        "birdnetpi-audio-analysis.service",
        "birdnetpi-audio-websocket.service",
        "birdnetpi-update.service",
    ]
    for service in birdnet_services:
        subprocess.run(
            ["sudo", "systemctl", "start", service],
            check=True,
            stdin=subprocess.DEVNULL,
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


def check_services_health() -> None:
    """Check that all services are running and healthy."""
    services = [
        "redis-server.service",
        "caddy.service",
        "birdnetpi-fastapi.service",
        "birdnetpi-audio-capture.service",
        "birdnetpi-audio-analysis.service",
        "birdnetpi-audio-websocket.service",
        "birdnetpi-update.service",
    ]

    all_healthy = True
    for service in services:
        status = check_service_status(service)
        if status != "✓":
            all_healthy = False
            log("✗", f"Service {service} is not running")

    if not all_healthy:
        raise RuntimeError("Not all services are healthy")


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

    # Check and enable SPI if needed (must be before any hardware detection)
    print()
    log("→", "Checking SPI interface for e-paper HAT support")
    needs_reboot = enable_spi_interface()
    if needs_reboot:
        print()
        print("=" * 60)
        print("REBOOT REQUIRED")
        print("=" * 60)
        print()
        print("SPI interface has been enabled for e-paper HAT support.")
        print("The system needs to reboot to apply this change.")
        print()
        print("After reboot, please run the installer again:")
        print("  cd /opt/birdnetpi && sudo -u birdnetpi .venv/bin/python install/setup_app.py")
        print()
        print("=" * 60)
        print()
        response = input("Reboot now? (y/n): ").strip().lower()
        if response == "y":
            subprocess.run(["sudo", "reboot"], check=True)
        else:
            print("Please reboot manually and re-run the installer.")
            sys.exit(0)
    log("✓", "SPI interface check complete")

    try:
        # Wave 1: System setup (parallel - apt-update already done in install.sh)
        print()
        log("→", "Starting: data directories, system packages")
        run_parallel(
            [
                ("Creating data directories", create_directories),
                ("Installing system packages", install_system_packages),
            ]
        )
        log("✓", "Completed: data directories, system packages")

        # Wave 2: Install uv (sequential, needs network after apt operations complete)
        print()
        log("→", "Installing uv package manager")
        install_uv()
        log("✓", "Installing uv package manager")

        # Wave 3: Python dependencies (sequential, needs uv)
        print()
        log("→", "Installing Python dependencies")
        install_python_dependencies()
        log("✓", "Installing Python dependencies")

        # Wave 4: Configuration and services (parallel, long-running tasks at bottom)
        print()
        log("→", "Starting: web/cache configuration, systemd services, asset download")
        run_parallel(
            [
                ("Configuring Redis cache server", configure_redis),
                ("Configuring Caddy web server", configure_caddy),
                ("Installing systemd services", install_systemd_services),
                (
                    "Downloading BirdNET assets (may take 1-10 minutes depending on connection)",
                    install_assets,
                ),
            ]
        )
        log("✓", "Completed: web/cache configuration, systemd services, asset download")

        # Wave 4.5: System configuration (sequential, before starting services)
        print()
        log("→", "Optimizing system for device")
        # Disable unnecessary services on low-memory devices
        device_specs = detect_device_specs()
        disable_unnecessary_services(device_specs["total_ram_mb"])
        log("✓", "Optimizing system for device")

        print()
        log("→", "Configuring system settings")
        setup_cmd = [
            "sudo",
            "-u",
            "birdnetpi",
            "/opt/birdnetpi/.venv/bin/setup-system",
        ]
        if not sys.stdin.isatty():
            setup_cmd.append("--non-interactive")
        result = subprocess.run(
            setup_cmd,
            env={**os.environ, "BIRDNETPI_DATA": "/var/lib/birdnetpi"},
            check=False,
            stdin=sys.stdin if sys.stdin.isatty() else subprocess.DEVNULL,
            capture_output=False,
        )
        if result.returncode != 0:
            raise RuntimeError("System setup failed")
        log("✓", "Configuring system settings")

        # Wave 5: Start services (sequential, after assets are ready)
        print()
        log("→", "Starting systemd services")
        start_systemd_services()
        log("✓", "Starting systemd services")

        # Wave 6: Health check
        print()
        log("→", "Checking service health")
        check_services_health()
        log("✓", "Checking service health")

        # Show final summary
        ip_address = get_ip_address()
        show_final_summary(ip_address)

    except Exception as e:
        log("✗", f"Installation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
