import os
import subprocess
import sys
from pathlib import Path


def setup_systemd_services(venv_path: Path) -> None:
    """Set up systemd services for the application."""
    print("\nSetting up systemd services...")
    systemd_dir = "/etc/systemd/system/"
    user = "birdnetpi"
    python_exec = venv_path / "bin" / "python3"
    repo_root = Path("/opt/birdnetpi")

    services = [
        {
            "name": "birdnet_caddy.service",
            "description": "Caddy Web Server",
            "after": "network-online.target",
            "exec_start": "/usr/bin/caddy run --config /etc/caddy/Caddyfile",
        },
        {
            "name": "birdnet_fastapi.service",
            "description": "BirdNET FastAPI Server",
            "after": "network-online.target",
            "exec_start": (
                f"{python_exec} -m uvicorn birdnetpi.web.main:app --host 0.0.0.0 --port 8000"
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
            "after": "network-online.target",
            "exec_start": f"{python_exec} -m birdnetpi.daemons.audio_capture_daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
        {
            "name": "birdnet_audio_analysis.service",
            "description": "BirdNET Audio Analysis",
            "after": "network-online.target",
            "exec_start": f"{python_exec} -m birdnetpi.daemons.audio_analysis_daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
        {
            "name": "birdnet_audio_websocket.service",
            "description": "BirdNET Audio Websocket",
            "after": "network-online.target",
            "exec_start": f"{python_exec} -m birdnetpi.daemons.audio_websocket_daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
        {
            "name": "birdnet_spectrogram_websocket.service",
            "description": "BirdNET Spectrogram Websocket",
            "after": "network-online.target",
            "exec_start": f"{python_exec} -m birdnetpi.daemons.spectrogram_websocket_daemon",
            "environment": "PYTHONPATH=/opt/birdnetpi/src",
        },
    ]

    for service_config in services:
        service_name = service_config["name"]
        service_file_path = os.path.join(systemd_dir, service_name)
        content = "[Unit]\n"
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
    print("Systemd services setup complete.")


def main() -> None:
    """Set up the BirdNET-Pi application."""
    if os.geteuid() == 0:
        print(
            "This script should not be run as root. "
            "Please run as a non-root user with sudo privileges."
        )
        sys.exit(1)

    # Install system dependencies
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    dependencies = [
        "ffmpeg",
        "sqlite3",
        "icecast2",
        "lsof",
        "net-tools",
        "alsa-utils",
        "pulseaudio",
        "avahi-utils",
        "sox",
        "libsox-fmt-mp3",
        "bc",
        "libjpeg-dev",
        "zlib1g-dev",
        "debian-keyring",
        "debian-archive-keyring",
        "apt-transport-https",
        "gnupg",
        "curl",
        "ca-certificates",
        "python3-venv",
        "caddy",
        "iproute2",
        "libportaudio2",
        "portaudio19-dev",
        "systemd-journal-remote",
    ]
    subprocess.run(
        ["sudo", "apt-get", "install", "-y", "--no-install-recommends", *dependencies],
        check=True,
    )

    # Configure Caddy
    subprocess.run(
        [
            "sudo",
            "curl",
            "-1sLf",
            "https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
            "-o",
            "/usr/share/keyrings/caddy-stable-archive-keyring.gpg",
        ],
        check=True,
    )
    subprocess.run(
        [
            "sudo",
            "sh",
            "-c",
            "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' "
            "| tee /etc/apt/sources.list.d/caddy-stable.list",
        ],
        check=True,
    )
    caddyfile = Path("/etc/caddy/Caddyfile")
    if not caddyfile.exists():
        subprocess.run(["sudo", "cp", "config_templates/Caddyfile", str(caddyfile)], check=True)
        subprocess.run(["sudo", "chown", "root:root", str(caddyfile)], check=True)

    # Create user and directories
    subprocess.run(["sudo", "useradd", "-m", "-s", "/bin/bash", "birdnetpi"], check=False)
    subprocess.run(["sudo", "usermod", "-aG", "audio,video,dialout", "birdnetpi"], check=True)
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

    # Use a virtual environment for the application
    venv_dir = Path("/opt/birdnetpi/.venv")
    if not venv_dir.exists():
        subprocess.run(
            ["sudo", "-u", "birdnetpi", "python3.11", "-m", "venv", str(venv_dir)], check=True
        )

    # Install Python dependencies
    pip_path = str(venv_dir / "bin" / "pip")
    subprocess.run(["sudo", "-u", "birdnetpi", pip_path, "install", "uv"], check=True)
    uv_path = str(venv_dir / "bin" / "uv")
    pyproject_path = Path("/opt/birdnetpi/pyproject.toml")
    if not pyproject_path.exists():
        subprocess.run(["sudo", "cp", "pyproject.toml", str(pyproject_path)], check=True)
        subprocess.run(["sudo", "chown", "birdnetpi:birdnetpi", str(pyproject_path)], check=True)

    uv_lock_path = Path("/opt/birdnetpi/uv.lock")
    if not uv_lock_path.exists():
        subprocess.run(["sudo", "cp", "uv.lock", str(uv_lock_path)], check=True)
        subprocess.run(["sudo", "chown", "birdnetpi:birdnetpi", str(uv_lock_path)], check=True)

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
        check=True,
    )

    # Copy source code
    subprocess.run(["sudo", "cp", "-r", "src/birdnetpi", "/opt/birdnetpi/"], check=True)
    subprocess.run(
        ["sudo", "chown", "-R", "birdnetpi:birdnetpi", "/opt/birdnetpi/birdnetpi"], check=True
    )

    # Install assets
    asset_installer_path = venv_dir / "bin" / "asset-installer"
    subprocess.run(
        [
            "sudo",
            "-u",
            "birdnetpi",
            str(asset_installer_path),
            "install",
            "v1.0.2",
            "--include-models",
            "--include-ioc-db",
        ],
        check=True,
    )

    # Setup systemd services
    setup_systemd_services(venv_dir)

    print("Installation complete.")


if __name__ == "__main__":
    main()
