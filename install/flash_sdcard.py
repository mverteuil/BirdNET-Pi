#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "click>=8.1.0",
#     "rich>=13.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""Flash Raspberry Pi OS to SD card and configure for BirdNET-Pi installation.

This script automates the process of creating a bootable Raspberry Pi OS SD card
configured for BirdNET-Pi installation, including WiFi setup, user configuration,
and optional auto-installer on first boot.

Usage:
    uv run install/flash_sdcard.py
"""

import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import click  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from rich.console import Console  # type: ignore[import-untyped]
from rich.panel import Panel  # type: ignore[import-untyped]
from rich.progress import (  # type: ignore[import-untyped]
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt  # type: ignore[import-untyped]
from rich.table import Table  # type: ignore[import-untyped]

console = Console()


def escape_toml_string(s: str) -> str:
    """Escape a string for use in TOML basic strings.

    Args:
        s: String to escape

    Returns:
        Escaped string safe for TOML
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def find_command(cmd: str, homebrew_paths: list[str] | None = None) -> str:
    """Find command in PATH or common Homebrew locations.

    Args:
        cmd: Command name to find (e.g., "xz", "gdd")
        homebrew_paths: Optional list of Homebrew paths to check

    Returns:
        Full path to command or command name (will fail later if not found)
    """
    # Try shutil.which first (checks PATH)
    if result := shutil.which(cmd):
        return result

    # Check common Homebrew locations on macOS
    if platform.system() == "Darwin":
        # For xz specifically, also check the Cellar (brew --prefix xz doesn't work in subprocess)
        if cmd == "xz":
            xz_cellar_paths = [
                "/opt/homebrew/Cellar/xz/5.8.1/bin/xz",  # Apple Silicon Cellar
                "/usr/local/Cellar/xz/5.8.1/bin/xz",  # Intel Mac Cellar
            ]
            for path in xz_cellar_paths:
                if Path(path).exists() and Path(path).is_file():
                    return path

        homebrew_paths = homebrew_paths or [
            "/opt/homebrew/bin",  # Apple Silicon
            "/opt/homebrew/opt/xz/bin",  # xz-specific path on Apple Silicon
            "/usr/local/bin",  # Intel Macs
            "/usr/local/opt/xz/bin",  # xz-specific path on Intel Macs
        ]
        for path in homebrew_paths:
            full_path = Path(path) / cmd
            if full_path.exists() and full_path.is_file():
                return str(full_path)

    # Fall back to command name (will fail if not in PATH)
    return cmd


# Raspberry Pi OS image URLs (Lite versions for headless server)
PI_IMAGES = {
    "Pi 5": {
        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
    },
    "Pi 4": {
        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
    },
    "Pi 3": {
        # Pi 3B+ and newer support 64-bit - using arm64 for ai-edge-litert compatibility
        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
    },
    "Pi Zero 2 W": {
        # Zero 2 W has same BCM2710A1 as Pi 3 - supports 64-bit
        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
    },
}

CONFIG_DIR = Path.home() / ".config" / "birdnetpi"
CONFIG_FILE = CONFIG_DIR / "image_options.json"


def load_saved_config() -> dict[str, Any] | None:
    """Load saved configuration from ~/.config/birdnetpi/image_options.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load saved config: {e}[/yellow]")
    return None


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to ~/.config/birdnetpi/image_options.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    console.print(f"[green]Configuration saved to {CONFIG_FILE}[/green]")


def parse_size_to_gb(size_str: str) -> float | None:
    """Parse size string like '15.9 GB' or '2.0 TB' to gigabytes."""
    try:
        match = re.match(r"([0-9.]+)\s*([KMGT]?B)", size_str)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2)

        multipliers = {
            "B": 1 / (1024**3),
            "KB": 1 / (1024**2),
            "MB": 1 / 1024,
            "GB": 1,
            "TB": 1024,
        }
        return value * multipliers.get(unit, 1)
    except (ValueError, AttributeError):
        return None


def list_macos_devices() -> list[dict[str, str]]:
    """List block devices on macOS using diskutil."""
    result = subprocess.run(["diskutil", "list"], capture_output=True, text=True, check=True)
    devices = []
    lines = result.stdout.splitlines()

    for i, line in enumerate(lines):
        # Match device identifier like /dev/disk2
        if match := re.match(r"^(/dev/disk\d+)\s+\((.+?), physical\):", line):
            device_path = match.group(1)
            device_type = match.group(2)  # "internal" or "external"

            # Skip internal system disk (disk0) - too dangerous
            if device_path == "/dev/disk0":
                continue

            # Size is on the partition scheme line (next few lines)
            size_str = "Unknown"
            for next_line in lines[i + 1 : i + 5]:  # Check next 4 lines
                if size_match := re.search(r"\*([0-9.]+\s*[KMGT]?B)", next_line):
                    size_str = size_match.group(1)
                    break

            # Include both external and internal physical disks (for SD card readers)
            # Filter out large internal drives (> 256GB likely not an SD card)
            if size_str != "Unknown":
                size_gb = parse_size_to_gb(size_str)
                if size_gb and size_gb <= 256:  # SD cards typically <= 256GB
                    display_type = "External" if device_type == "external" else "SD Card Reader"
                    devices.append({"device": device_path, "size": size_str, "type": display_type})

    return devices


def list_block_devices() -> list[dict[str, str]]:
    """List available block devices (SD cards) on the system."""
    if platform.system() == "Darwin":
        return list_macos_devices()
    elif platform.system() == "Linux":
        # Linux
        result = subprocess.run(
            ["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE"],
            capture_output=True,
            text=True,
            check=True,
        )
        devices = []

        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "disk":
                # Filter for removable devices (SD cards, USB)
                device = f"/dev/{parts[0]}"
                try:
                    removable_check = subprocess.run(
                        ["cat", f"/sys/block/{parts[0]}/removable"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if removable_check.stdout.strip() == "1":
                        devices.append({"device": device, "size": parts[1], "type": "Removable"})
                except Exception:
                    pass

        return devices
    else:
        console.print("[red]Unsupported operating system[/red]")
        sys.exit(1)


def select_device() -> str:
    """Prompt user to select a block device to flash."""
    devices = list_block_devices()

    if not devices:
        console.print("[red]No removable devices found![/red]")
        sys.exit(1)

    console.print()
    console.print("[bold cyan]Available Devices:[/bold cyan]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Index", style="dim")
    table.add_column("Device", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Type")

    for idx, device in enumerate(devices, 1):
        table.add_row(str(idx), device["device"], device["size"], device["type"])

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[bold]Select device to flash[/bold]",
        choices=[str(i) for i in range(1, len(devices) + 1)],
    )

    selected = devices[int(choice) - 1]
    console.print()
    console.print(
        Panel(
            f"[bold yellow]WARNING: ALL DATA ON {selected['device']} WILL BE ERASED![/bold yellow]",
            border_style="red",
        )
    )

    if not Confirm.ask(f"Are you sure you want to flash {selected['device']}?"):
        console.print("[yellow]Cancelled[/yellow]")
        sys.exit(0)

    return selected["device"]


def select_pi_version() -> str:
    """Prompt user to select Raspberry Pi version."""
    console.print()
    console.print("[bold cyan]Select Raspberry Pi Version:[/bold cyan]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Index", style="dim")
    table.add_column("Model", style="green")

    # Map version numbers to model names for intuitive selection
    version_map = {
        "5": "Pi 5",
        "4": "Pi 4",
        "3": "Pi 3",
        "0": "Pi Zero 2 W",
    }

    # Display in ascending order (0, 3, 4, 5)
    for version in ["0", "3", "4", "5"]:
        model = version_map[version]
        table.add_row(version, model)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[bold]Select Raspberry Pi model[/bold]",
        choices=list(version_map.keys()),
    )

    return version_map[choice]


def download_image(pi_version: str, download_dir: Path) -> Path:
    """Download Raspberry Pi OS image if not already cached."""
    image_info = PI_IMAGES[pi_version]
    url = image_info["url"]
    filename = url.split("/")[-1]
    filepath = download_dir / filename

    if filepath.exists():
        console.print(f"[green]Using cached image: {filepath}[/green]")
        return filepath

    console.print(f"[cyan]Downloading Raspberry Pi OS image for {pi_version}...[/cyan]")

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        task = progress.add_task(f"Downloading {filename}", total=total)

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                progress.update(task, advance=len(chunk))

    console.print(f"[green]Downloaded: {filepath}[/green]")
    return filepath


def get_config_from_prompts(saved_config: dict[str, Any] | None) -> dict[str, Any]:  # noqa: C901
    """Prompt user for configuration options."""
    config: dict[str, Any] = {}

    console.print()
    console.print("[bold cyan]SD Card Configuration:[/bold cyan]")
    console.print()

    # WiFi settings
    if saved_config and "enable_wifi" in saved_config:
        config["enable_wifi"] = saved_config["enable_wifi"]
        console.print(f"[dim]Using saved WiFi enabled: {config['enable_wifi']}[/dim]")
    else:
        config["enable_wifi"] = Confirm.ask("Enable WiFi?", default=False)

    if config["enable_wifi"]:
        if saved_config and "wifi_ssid" in saved_config:
            config["wifi_ssid"] = saved_config["wifi_ssid"]
            console.print(f"[dim]Using saved WiFi SSID: {config['wifi_ssid']}[/dim]")
        else:
            config["wifi_ssid"] = Prompt.ask("WiFi SSID")

        if saved_config and "wifi_auth" in saved_config:
            config["wifi_auth"] = saved_config["wifi_auth"]
            console.print(f"[dim]Using saved WiFi Auth: {config['wifi_auth']}[/dim]")
        else:
            config["wifi_auth"] = Prompt.ask(
                "WiFi Auth Type", choices=["WPA", "WPA2", "WPA3"], default="WPA2"
            )

        if saved_config and "wifi_password" in saved_config:
            config["wifi_password"] = saved_config["wifi_password"]
            console.print("[dim]Using saved WiFi password[/dim]")
        else:
            config["wifi_password"] = Prompt.ask("WiFi Password", password=True)

    # User settings
    if saved_config and "admin_user" in saved_config:
        config["admin_user"] = saved_config["admin_user"]
        console.print(f"[dim]Using saved admin user: {config['admin_user']}[/dim]")
    else:
        config["admin_user"] = Prompt.ask("Device Admin", default="birdnetpi")

    if saved_config and "admin_password" in saved_config:
        config["admin_password"] = saved_config["admin_password"]
        console.print("[dim]Using saved admin password[/dim]")
    else:
        config["admin_password"] = Prompt.ask("Device Password", password=True)

    if saved_config and "hostname" in saved_config:
        config["hostname"] = saved_config["hostname"]
        console.print(f"[dim]Using saved hostname: {config['hostname']}[/dim]")
    else:
        config["hostname"] = Prompt.ask("Device Hostname", default="birdnetpi")

    # Advanced settings
    if saved_config and "gpio_debug" in saved_config:
        config["gpio_debug"] = saved_config["gpio_debug"]
        console.print(f"[dim]Using saved GPIO debug: {config['gpio_debug']}[/dim]")
    else:
        config["gpio_debug"] = Confirm.ask("Enable GPIO Debugging (Advanced)?", default=False)

    if saved_config and "copy_installer" in saved_config:
        config["copy_installer"] = saved_config["copy_installer"]
        console.print(f"[dim]Using saved copy installer: {config['copy_installer']}[/dim]")
    else:
        config["copy_installer"] = Confirm.ask("Copy install.sh?", default=True)

    return config


def flash_image(image_path: Path, device: str) -> None:
    """Flash the image to the SD card."""
    console.print()
    console.print(f"[cyan]Flashing {image_path.name} to {device}...[/cyan]")

    # Record start time
    start_time = time.time()

    # Unmount device first
    if platform.system() == "Darwin":
        subprocess.run(["diskutil", "unmountDisk", device], check=True, stdout=subprocess.DEVNULL)

    # Detect GNU dd (gdd) vs BSD dd on macOS
    dd_cmd = "dd"
    dd_bs = "bs=4m"  # BSD dd format
    dd_extra_args = []

    if platform.system() == "Darwin":
        # Check if GNU dd (gdd) is available from coreutils
        gdd_path = find_command("gdd")
        if gdd_path != "gdd":  # Found full path, not just the name
            dd_cmd = gdd_path
            dd_bs = "bs=4M"  # GNU dd format
            dd_extra_args = ["status=progress"]  # GNU dd supports progress
            console.print("[dim]Using GNU dd (gdd) for progress reporting[/dim]")

    # Decompress and flash
    if image_path.suffix == ".xz":
        console.print(
            "[yellow]Decompressing and flashing (this may take several minutes)...[/yellow]"
        )
        # Use shell pipeline: xz -dc image.xz | dd of=device
        # xz -dc = decompress to stdout
        xz_cmd = find_command("xz")
        console.print(f"[dim]Using xz at: {xz_cmd}[/dim]")

        # Verify the command exists
        if not Path(xz_cmd).exists() and xz_cmd == "xz":
            console.print("[red]Error: xz command not found in PATH or Homebrew locations[/red]")
            console.print("[yellow]Checking common paths:[/yellow]")
            for check_path in [
                "/opt/homebrew/bin/xz",
                "/opt/homebrew/opt/xz/bin/xz",
                "/usr/local/bin/xz",
            ]:
                exists = Path(check_path).exists()
                console.print(f"  {check_path}: {'✓ exists' if exists else '✗ not found'}")
            sys.exit(1)

        with subprocess.Popen([xz_cmd, "-dc", str(image_path)], stdout=subprocess.PIPE) as xz_proc:
            subprocess.run(
                ["sudo", dd_cmd, f"of={device}", dd_bs, *dd_extra_args],
                stdin=xz_proc.stdout,
                check=True,
            )
    else:
        subprocess.run(
            ["sudo", dd_cmd, f"if={image_path}", f"of={device}", dd_bs, *dd_extra_args],
            check=True,
        )

    subprocess.run(["sync"], check=True)

    # Calculate and display flash duration
    end_time = time.time()
    duration = end_time - start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    if minutes > 0:
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = f"{seconds}s"

    console.print(f"[green]✓ Image flashed successfully in {duration_str}[/green]")


def configure_boot_partition(device: str, config: dict[str, Any]) -> None:  # noqa: C901
    """Configure the bootfs partition with user settings."""
    console.print()
    console.print("[cyan]Configuring boot partition...[/cyan]")

    # Mount bootfs partition
    if platform.system() == "Darwin":
        # On macOS, the partition auto-mounts to /Volumes/bootfs
        boot_mount = Path("/Volumes/bootfs")
        if not boot_mount.exists():
            subprocess.run(["diskutil", "mount", f"{device}s1"], check=True)
            # Wait for mount
            import time

            time.sleep(2)
    else:
        # On Linux, manually mount
        boot_mount = Path("/mnt/bootfs")
        boot_mount.mkdir(parents=True, exist_ok=True)
        subprocess.run(["sudo", "mount", f"{device}1", str(boot_mount)], check=True)

    try:
        # Create custom.toml for first-boot configuration (Bookworm official method)
        # This configures user, SSH, and optionally WiFi on first boot
        # Use proper TOML string escaping for special characters
        hostname = escape_toml_string(config.get("hostname", "birdnetpi"))
        admin_user = escape_toml_string(config["admin_user"])
        admin_password = escape_toml_string(config["admin_password"])

        toml_content = f"""[system]
hostname = "{hostname}"

[user]
name = "{admin_user}"
password = "{admin_password}"
password_encrypted = false

[ssh]
enabled = true
"""

        # Add WiFi configuration if enabled
        if config.get("enable_wifi"):
            wifi_ssid = escape_toml_string(config["wifi_ssid"])
            wifi_password = escape_toml_string(config["wifi_password"])
            toml_content += f"""
[wlan]
ssid = "{wifi_ssid}"
password = "{wifi_password}"
password_encrypted = false
hidden = false
country = "US"
"""

        # Write custom.toml to temp file then copy with sudo
        temp_toml = Path("/tmp/birdnetpi_custom.toml")
        temp_toml.write_text(toml_content)
        subprocess.run(
            ["sudo", "cp", str(temp_toml), str(boot_mount / "custom.toml")],
            check=True,
        )
        temp_toml.unlink()

        config_summary = f"User: {config['admin_user']}, SSH: enabled"
        if config.get("enable_wifi"):
            config_summary += f", WiFi: {config['wifi_ssid']}"
        console.print(f"[green]✓ First-boot configuration: {config_summary}[/green]")

        # DEPRECATED: Old userconf.txt and firstrun.sh methods (kept for reference)
        # Bookworm now uses custom.toml instead
        if False and config.get("enable_wifi"):
            # Create a firstrun.sh script that creates a NetworkManager connection file
            # This is more reliable than running nmcli during early boot
            wifi_ssid = config["wifi_ssid"]
            wifi_password = config["wifi_password"]

            # Generate UUID for the connection
            import uuid

            connection_uuid = str(uuid.uuid4())

            firstrun_content = f"""#!/bin/bash

set +e

# Unblock WiFi
rfkill unblock wlan

# Set WiFi country
COUNTRY=US
if [ -e /usr/bin/raspi-config ]; then
    raspi-config nonint do_wifi_country "$COUNTRY"
fi

# Create NetworkManager connection file for WiFi
cat > /etc/NetworkManager/system-connections/preconfigured.nmconnection << 'NMEOF'
[connection]
id=preconfigured
uuid={connection_uuid}
type=wifi
interface-name=wlan0

[wifi]
mode=infrastructure
ssid={wifi_ssid}

[wifi-security]
auth-alg=open
key-mgmt=wpa-psk
psk={wifi_password}

[ipv4]
method=auto

[ipv6]
addr-gen-mode=default
method=auto

[proxy]
NMEOF

# Set proper permissions (NetworkManager requires 600)
chmod 600 /etc/NetworkManager/system-connections/preconfigured.nmconnection

# Clean up firstrun
rm -f /boot/firmware/firstrun.sh
sed -i 's| systemd.run=/boot/firmware/firstrun.sh||g' /boot/firmware/cmdline.txt
exit 0
"""
            temp_firstrun = Path("/tmp/birdnetpi_firstrun.sh")
            temp_firstrun.write_text(firstrun_content)

            # Copy to boot partition
            firstrun_dest = boot_mount / "firstrun.sh"
            subprocess.run(
                ["sudo", "cp", str(temp_firstrun), str(firstrun_dest)],
                check=True,
            )
            # Make executable
            subprocess.run(
                ["sudo", "chmod", "+x", str(firstrun_dest)],
                check=True,
            )

            # Modify cmdline.txt to run firstrun.sh on boot
            cmdline_path = boot_mount / "cmdline.txt"
            result = subprocess.run(
                ["sudo", "cat", str(cmdline_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            cmdline = result.stdout.strip()

            # Add systemd.run parameter if not already present
            if "systemd.run=/boot/firmware/firstrun.sh" not in cmdline:
                cmdline += (
                    " systemd.run=/boot/firmware/firstrun.sh"
                    " systemd.unit=kernel-command-line.target"
                )
                temp_cmdline = Path("/tmp/birdnetpi_cmdline.txt")
                temp_cmdline.write_text(cmdline)
                subprocess.run(
                    ["sudo", "cp", str(temp_cmdline), str(cmdline_path)],
                    check=True,
                )
                temp_cmdline.unlink()

            temp_firstrun.unlink()
            console.print(f"[green]✓ WiFi configured (SSID: {config['wifi_ssid']})[/green]")

        # GPIO debugging
        if config.get("gpio_debug"):
            # Append to config.txt using shell redirection with sudo
            gpio_config = "\n# GPIO Debugging\nenable_uart=1\n"
            subprocess.run(
                ["sudo", "bash", "-c", f"echo '{gpio_config}' >> {boot_mount / 'config.txt'}"],
                check=True,
            )
            console.print("[green]✓ GPIO debugging enabled[/green]")

        # Copy installer script if requested
        if config.get("copy_installer"):
            install_script = Path(__file__).parent / "install.sh"
            if install_script.exists():
                subprocess.run(
                    ["sudo", "cp", str(install_script), str(boot_mount / "install.sh")],
                    check=True,
                )
                console.print("[green]✓ install.sh copied to boot partition[/green]")
            else:
                console.print(
                    "[yellow]Warning: install.sh not found, skipping installer copy[/yellow]"
                )

    finally:
        # Unmount
        if platform.system() == "Darwin":
            subprocess.run(["diskutil", "unmount", str(boot_mount)], check=True)
        else:
            subprocess.run(["sudo", "umount", str(boot_mount)], check=True)

    console.print("[green]✓ Boot partition configured[/green]")


@click.command()
@click.option(
    "--save-config", "save_config_flag", is_flag=True, help="Save configuration for future use"
)
def main(save_config_flag: bool) -> None:
    """Flash Raspberry Pi OS to SD card and configure for BirdNET-Pi."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]BirdNET-Pi SD Card Flasher[/bold cyan]\n"
            "[dim]Create bootable Raspberry Pi OS SD cards configured for BirdNET-Pi[/dim]",
            border_style="cyan",
        )
    )

    # Load saved configuration
    saved_config = load_saved_config()
    if saved_config:
        console.print(f"[green]Found saved configuration at {CONFIG_FILE}[/green]")

    # Select device
    device = select_device()

    # Select Pi version
    pi_version = select_pi_version()

    # Download image
    download_dir = Path.home() / ".cache" / "birdnetpi" / "images"
    download_dir.mkdir(parents=True, exist_ok=True)
    image_path = download_image(pi_version, download_dir)

    # Get configuration
    config = get_config_from_prompts(saved_config)

    # Save configuration if requested
    if save_config_flag or (
        not saved_config and Confirm.ask("Save this configuration for future use?")
    ):
        save_config(config)

    # Flash image
    console.print()
    console.print(
        Panel.fit(
            "[bold yellow]Administrator Access Required[/bold yellow]\n\n"
            "The next steps will flash and configure the SD card.\n"
            "You may be prompted to enter your [cyan]system password[/cyan] "
            "[bold]multiple times[/bold].\n\n"
            "[dim]This is normal and safe - the password is only used to "
            "write to the SD card.[/dim]",
            border_style="yellow",
        )
    )
    flash_image(image_path, device)

    # Configure boot partition
    configure_boot_partition(device, config)

    # Eject SD card
    console.print()
    console.print("[cyan]Ejecting SD card...[/cyan]")
    if platform.system() == "Darwin":
        subprocess.run(["diskutil", "eject", device], check=True)
    else:
        subprocess.run(["sudo", "eject", device], check=True)

    console.print()

    # Build summary message
    summary_parts = [
        "[bold green]✓ SD Card Ready![/bold green]\n",
        f"Raspberry Pi Model: [yellow]{pi_version}[/yellow]",
        f"Hostname: [cyan]{config.get('hostname', 'birdnetpi')}[/cyan]",
        f"Admin User: [cyan]{config['admin_user']}[/cyan]",
        "SSH: [green]Enabled[/green]",
    ]

    # Add WiFi status
    if config.get("enable_wifi"):
        summary_parts.append(f"WiFi: [green]Configured ({config['wifi_ssid']})[/green]")
    else:
        summary_parts.append("WiFi: [yellow]Not configured (Ethernet required)[/yellow]")

    # Add installer script status
    if config.get("copy_installer"):
        summary_parts.append("Installer: [green]Copied to /boot/firmware/install.sh[/green]\n")
        summary_parts.append(
            "[dim]Insert the SD card into your Raspberry Pi and power it on.\n"
            "First boot will configure the system.\n"
            "Then SSH in and run: [cyan]bash /boot/firmware/install.sh[/cyan][/dim]"
        )
    else:
        summary_parts.append("Installer: [yellow]Not copied[/yellow]\n")
        summary_parts.append(
            "[dim]Insert the SD card into your Raspberry Pi and power it on.\n"
            "First boot will configure the system.[/dim]"
        )

    console.print(
        Panel.fit(
            "\n".join(summary_parts),
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
