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


# Raspberry Pi OS and Armbian image URLs (Lite/Minimal versions for headless server)
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
    "Le Potato (Raspbian)": {
        # LibreComputer AML-S905X-CC - uses same arm64 image as Pi, requires portability script
        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
        "requires_portability": True,
    },
    "Le Potato (Armbian)": {
        # LibreComputer AML-S905X-CC - Native Armbian Bookworm minimal
        # URL format: https://dl.armbian.com/lepotato/Bookworm_current_minimal
        # This redirects to the latest stable build with .sha file available
        "url": "https://dl.armbian.com/lepotato/Bookworm_current_minimal",
        "is_armbian": True,  # Will download and verify .sha file from same location
    },
}

CONFIG_DIR = Path.home() / ".config" / "birdnetpi"
PROFILES_DIR = CONFIG_DIR / "profiles"


def list_profiles() -> list[dict[str, Any]]:
    """List all saved profiles with metadata.

    Returns:
        List of profile dicts with 'name', 'path', and 'config' keys
    """
    if not PROFILES_DIR.exists():
        return []

    profiles = []
    for profile_file in sorted(PROFILES_DIR.glob("*.json")):
        try:
            with open(profile_file) as f:
                config = json.load(f)
                profiles.append(
                    {
                        "name": profile_file.stem,
                        "path": profile_file,
                        "config": config,
                    }
                )
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not load profile {profile_file.name}: {e}[/yellow]"
            )

    return profiles


def load_profile(profile_name: str) -> dict[str, Any] | None:
    """Load a specific profile by name.

    Args:
        profile_name: Name of the profile to load

    Returns:
        Profile configuration dict or None if not found
    """
    profile_path = PROFILES_DIR / f"{profile_name}.json"
    if profile_path.exists():
        try:
            with open(profile_path) as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load profile {profile_name}: {e}[/yellow]")
    return None


def save_profile(profile_name: str, config: dict[str, Any]) -> None:
    """Save configuration as a named profile.

    Args:
        profile_name: Name for the profile
        config: Configuration dict to save
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = PROFILES_DIR / f"{profile_name}.json"
    with open(profile_path, "w") as f:
        json.dump(config, f, indent=2)
    console.print(f"[green]Profile '{profile_name}' saved to {profile_path}[/green]")


def select_profile() -> tuple[dict[str, Any] | None, str | None, bool]:
    """Display available profiles and let user select one (supports 0-9).

    Returns:
        Tuple of (selected profile config or None, profile name or None, should_edit flag)
    """
    profiles = list_profiles()

    if not profiles:
        return None, None, False

    # Limit to first 10 profiles (0-9)
    profiles = profiles[:10]

    console.print()
    console.print("[bold cyan]Saved Profiles:[/bold cyan]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Key", style="dim")
    table.add_column("Profile Name", style="green")
    table.add_column("Device Type", justify="left")
    table.add_column("Hostname", justify="left")
    table.add_column("WiFi SSID", justify="left")

    for idx, profile in enumerate(profiles):
        config = profile["config"]
        device_type = config.get("device_type", "Not set")
        hostname = config.get("hostname", "N/A")
        wifi_ssid = config.get("wifi_ssid", "Not configured")
        table.add_row(str(idx), profile["name"], device_type, hostname, wifi_ssid)

    console.print(table)
    console.print()

    choices = [str(i) for i in range(len(profiles))] + ["n"]
    choice = Prompt.ask(
        "[bold]Select profile (0-9) or 'n' for new configuration[/bold]",
        choices=choices,
        default="n",
    )

    if choice == "n":
        return None, None, False

    selected_profile = profiles[int(choice)]
    profile_name = selected_profile["name"]
    console.print(f"[green]Selected profile: {profile_name}[/green]")

    # Ask if user wants to use as-is or edit
    action = Prompt.ask(
        "[bold]Use profile as-is or edit/duplicate?[/bold]",
        choices=["use", "edit"],
        default="use",
    )

    should_edit = action == "edit"
    if should_edit:
        console.print(
            "[cyan]You can now edit the configuration (press Enter to keep existing values)[/cyan]"
        )

    return selected_profile["config"], profile_name, should_edit


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


def select_device(device_index: int | None = None) -> str:
    """Prompt user to select a block device to flash.

    Args:
        device_index: Optional 1-based index to select device without prompting

    Returns:
        Selected device path (e.g., "/dev/disk2")
    """
    devices = list_block_devices()

    if not devices:
        console.print("[red]No removable devices found![/red]")
        sys.exit(1)

    # If device_index provided, validate and use it
    if device_index is not None:
        if device_index < 1 or device_index > len(devices):
            console.print(f"[red]Invalid device index: {device_index}[/red]")
            console.print(f"[yellow]Available indices: 1-{len(devices)}[/yellow]")
            sys.exit(1)

        selected = devices[device_index - 1]
        console.print(f"[cyan]Using device {device_index}: {selected['device']}[/cyan]")

        console.print()
        console.print(
            Panel(
                f"[bold yellow]WARNING: ALL DATA ON {selected['device']} "
                "WILL BE ERASED![/bold yellow]",
                border_style="red",
            )
        )
        return selected["device"]

    # Otherwise, prompt user to select
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


def select_pi_version(
    saved_device_type: str | None = None,
    device_type_override: str | None = None,
    edit_mode: bool = False,
) -> str:
    """Prompt user to select device model.

    Args:
        saved_device_type: Device type from saved profile
        device_type_override: CLI override for device type
        edit_mode: If True, show prompts with defaults; if False, auto-use saved values

    Returns:
        Selected device model name (e.g., "Pi 4", "Le Potato (Armbian)")
    """
    # Use override if provided
    if device_type_override:
        if device_type_override not in PI_IMAGES:
            console.print(f"[red]Invalid device type: {device_type_override}[/red]")
            console.print(f"[yellow]Available types: {', '.join(PI_IMAGES.keys())}[/yellow]")
            sys.exit(1)
        console.print(f"[cyan]Using device type from CLI: {device_type_override}[/cyan]")
        return device_type_override

    # Use saved value if not in edit mode
    if saved_device_type and not edit_mode:
        if saved_device_type in PI_IMAGES:
            console.print(f"[dim]Using saved device type: {saved_device_type}[/dim]")
            return saved_device_type
        else:
            console.print(
                f"[yellow]Warning: Saved device type '{saved_device_type}' not found[/yellow]"
            )

    # Prompt user to select
    console.print()
    console.print("[bold cyan]Select Device Model:[/bold cyan]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Index", style="dim")
    table.add_column("Model", style="green")
    table.add_column("Notes", style="dim")

    # Map version numbers to model names for intuitive selection
    version_map = {
        "5": "Pi 5",
        "4": "Pi 4",
        "3": "Pi 3",
        "0": "Pi Zero 2 W",
        "R": "Le Potato (Raspbian)",
        "A": "Le Potato (Armbian)",
    }

    # Display in order (0, 3, 4, 5, R, A)
    display_order = [
        ("0", "Pi Zero 2 W", ""),
        ("3", "Pi 3", ""),
        ("4", "Pi 4", ""),
        ("5", "Pi 5", ""),
        ("R", "Le Potato (Raspbian)", "Two-step boot required"),
        ("A", "Le Potato (Armbian)", "Native Armbian, direct boot"),
    ]

    for version, model, notes in display_order:
        table.add_row(version, model, notes)

    console.print(table)
    console.print()

    # Use saved value as default in edit mode
    default_choice = None
    if edit_mode and saved_device_type:
        # Find the key for the saved device type
        for key, model in version_map.items():
            if model == saved_device_type:
                default_choice = key
                break

    choice = Prompt.ask(
        "[bold]Select device model[/bold]",
        choices=list(version_map.keys()),
        default=default_choice,
        show_default=bool(default_choice),
    )

    return version_map[choice]


def download_image(pi_version: str, download_dir: Path) -> Path:
    """Download Raspberry Pi OS or Armbian image if not already cached.

    Args:
        pi_version: Device model name (e.g., "Pi 4", "Le Potato (Armbian)")
        download_dir: Directory to store downloaded images

    Returns:
        Path to the downloaded image file
    """
    image_info = PI_IMAGES[pi_version]
    url = image_info["url"]
    is_armbian = image_info.get("is_armbian", False)

    # For Armbian, follow redirects to get actual download URL
    if is_armbian:
        console.print(f"[cyan]Resolving Armbian image URL for {pi_version}...[/cyan]")
        # HEAD request to follow redirects and get actual filename
        # SSL verification is enabled - redirect should have valid cert
        head_response = requests.head(url, allow_redirects=True, timeout=30)
        head_response.raise_for_status()

        # Extract final URL and filename after redirect
        final_url = head_response.url
        url = final_url  # Use the actual file URL for download
        filename = final_url.split("/")[-1]

        console.print(f"[dim]Resolved to: {filename}[/dim]")
    else:
        filename = url.split("/")[-1]

    filepath = download_dir / filename

    if filepath.exists():
        console.print(f"[green]Using cached image: {filepath}[/green]")
        return filepath

    console.print(f"[cyan]Downloading image for {pi_version}...[/cyan]")

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        # Download with SSL verification enabled
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        task = progress.add_task(f"Downloading {filename}", total=total)

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                progress.update(task, advance=len(chunk))

    console.print(f"[green]Downloaded: {filepath}[/green]")

    # Verify SHA256 for Armbian (download .sha file from same location)
    if is_armbian:
        console.print("[cyan]Verifying image integrity...[/cyan]")
        sha_url = f"{url}.sha"
        try:
            sha_response = requests.get(sha_url, timeout=30)
            sha_response.raise_for_status()
            # SHA file format: "hash filename"
            expected_sha = sha_response.text.strip().split()[0]

            # Calculate actual SHA256
            import hashlib

            sha256_hash = hashlib.sha256()
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(byte_block)
            actual_sha = sha256_hash.hexdigest()

            if actual_sha == expected_sha:
                console.print("[green]✓ SHA256 verification passed[/green]")
            else:
                console.print("[red]✗ SHA256 verification failed![/red]")
                console.print(f"[red]Expected: {expected_sha}[/red]")
                console.print(f"[red]Got: {actual_sha}[/red]")
                filepath.unlink()  # Delete corrupted file
                sys.exit(1)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not verify SHA256: {e}[/yellow]")
            console.print("[yellow]Proceeding anyway, but file integrity is not verified[/yellow]")

    return filepath


def get_config_from_prompts(  # noqa: C901
    saved_config: dict[str, Any] | None,
    edit_mode: bool = False,
) -> dict[str, Any]:
    """Prompt user for configuration options.

    Args:
        saved_config: Previously saved configuration to use as defaults
        edit_mode: If True, show prompts with defaults; if False, auto-use saved values
    """
    config: dict[str, Any] = {}

    console.print()
    console.print("[bold cyan]SD Card Configuration:[/bold cyan]")
    console.print()

    # WiFi settings
    if saved_config and "enable_wifi" in saved_config and not edit_mode:
        config["enable_wifi"] = saved_config["enable_wifi"]
        console.print(f"[dim]Using saved WiFi enabled: {config['enable_wifi']}[/dim]")
    else:
        default_wifi = saved_config.get("enable_wifi", False) if saved_config else False
        config["enable_wifi"] = Confirm.ask("Enable WiFi?", default=default_wifi)

    if config["enable_wifi"]:
        if saved_config and "wifi_ssid" in saved_config and not edit_mode:
            config["wifi_ssid"] = saved_config["wifi_ssid"]
            console.print(f"[dim]Using saved WiFi SSID: {config['wifi_ssid']}[/dim]")
        else:
            default_ssid = saved_config.get("wifi_ssid", "") if saved_config else ""
            config["wifi_ssid"] = Prompt.ask("WiFi SSID", default=default_ssid or "")

        if saved_config and "wifi_auth" in saved_config and not edit_mode:
            config["wifi_auth"] = saved_config["wifi_auth"]
            console.print(f"[dim]Using saved WiFi Auth: {config['wifi_auth']}[/dim]")
        else:
            default_auth = saved_config.get("wifi_auth", "WPA2") if saved_config else "WPA2"
            config["wifi_auth"] = Prompt.ask(
                "WiFi Auth Type", choices=["WPA", "WPA2", "WPA3"], default=default_auth
            )

        if saved_config and "wifi_password" in saved_config and not edit_mode:
            config["wifi_password"] = saved_config["wifi_password"]
            console.print("[dim]Using saved WiFi password[/dim]")
        else:
            default_pass = saved_config.get("wifi_password", "") if saved_config else ""
            config["wifi_password"] = Prompt.ask(
                "WiFi Password", password=True, default=default_pass
            )

    # User settings
    if saved_config and "admin_user" in saved_config and not edit_mode:
        config["admin_user"] = saved_config["admin_user"]
        console.print(f"[dim]Using saved admin user: {config['admin_user']}[/dim]")
    else:
        default_user = saved_config.get("admin_user", "birdnetpi") if saved_config else "birdnetpi"
        config["admin_user"] = Prompt.ask("Device Admin", default=default_user)

    if saved_config and "admin_password" in saved_config and not edit_mode:
        config["admin_password"] = saved_config["admin_password"]
        console.print("[dim]Using saved admin password[/dim]")
    else:
        default_pass = saved_config.get("admin_password", "") if saved_config else ""
        config["admin_password"] = Prompt.ask(
            "Device Password", password=True, default=default_pass
        )

    if saved_config and "hostname" in saved_config and not edit_mode:
        config["hostname"] = saved_config["hostname"]
        console.print(f"[dim]Using saved hostname: {config['hostname']}[/dim]")
    else:
        default_hostname = (
            saved_config.get("hostname", "birdnetpi") if saved_config else "birdnetpi"
        )
        config["hostname"] = Prompt.ask("Device Hostname", default=default_hostname)

    # Advanced settings
    if saved_config and "gpio_debug" in saved_config and not edit_mode:
        config["gpio_debug"] = saved_config["gpio_debug"]
        console.print(f"[dim]Using saved GPIO debug: {config['gpio_debug']}[/dim]")
    else:
        default_gpio = saved_config.get("gpio_debug", False) if saved_config else False
        config["gpio_debug"] = Confirm.ask(
            "Enable GPIO Debugging (Advanced)?", default=default_gpio
        )

    if saved_config and "copy_installer" in saved_config and not edit_mode:
        config["copy_installer"] = saved_config["copy_installer"]
        console.print(f"[dim]Using saved copy installer: {config['copy_installer']}[/dim]")
    else:
        default_copy = saved_config.get("copy_installer", True) if saved_config else True
        config["copy_installer"] = Confirm.ask("Copy install.sh?", default=default_copy)

    if saved_config and "enable_spi" in saved_config and not edit_mode:
        config["enable_spi"] = saved_config["enable_spi"]
        console.print(f"[dim]Using saved SPI enabled: {config['enable_spi']}[/dim]")
    else:
        default_spi = saved_config.get("enable_spi", False) if saved_config else False
        config["enable_spi"] = Confirm.ask("Enable SPI (for ePaper HAT)?", default=default_spi)

    # BirdNET-Pi pre-configuration (optional)
    console.print()
    console.print("[bold cyan]BirdNET-Pi Configuration (Optional):[/bold cyan]")
    console.print("[dim]Pre-configure BirdNET-Pi for headless installation[/dim]")
    console.print()

    # Sentinel for missing/empty values
    unset = object()

    # Configuration prompts - only shown if previous field was provided
    birdnet_prompts = {
        "birdnet_device_name": {
            "prompt": "Device Name",
            "help": None,
            "condition": None,
        },
        "birdnet_latitude": {
            "prompt": "Latitude",
            "help": None,
            "condition": None,
        },
        "birdnet_longitude": {
            "prompt": "Longitude",
            "help": None,
            "condition": "birdnet_latitude",  # Only ask if latitude provided
        },
        "birdnet_timezone": {
            "prompt": "Timezone",
            "help": [
                "Common timezones:",
                "  Americas: America/New_York, America/Chicago, America/Los_Angeles",
                "  Europe: Europe/London, Europe/Paris, Europe/Berlin",
                "  Asia: Asia/Tokyo, Asia/Shanghai, Asia/Kolkata",
                "  Pacific: Pacific/Auckland, Australia/Sydney",
            ],
            "condition": "birdnet_longitude",  # Only ask if longitude provided
        },
        "birdnet_language": {
            "prompt": "Language Code",
            "help": ["Common languages: en, es, fr, de, it, pt, nl, ru, zh, ja"],
            "condition": None,
        },
    }

    for key, prompt_config in birdnet_prompts.items():
        # Check if condition is met (if any)
        condition = prompt_config["condition"]
        if condition and not config.get(condition):
            continue

        # Check for saved value (must not be None or empty string)
        saved_value = saved_config.get(key, unset) if saved_config else unset
        if saved_value is not unset and saved_value not in (None, "") and not edit_mode:
            config[key] = saved_value
            console.print(
                f"[dim]Using saved {prompt_config['prompt'].lower()}: {saved_value}[/dim]"
            )
        else:
            # Show help text if provided
            if prompt_config["help"]:
                console.print()
                for line in prompt_config["help"]:
                    console.print(f"[dim]{line}[/dim]")

            # Get default value for edit mode
            default_value = ""
            if edit_mode and saved_value is not unset and saved_value not in (None, ""):
                default_value = str(saved_value)

            # Prompt user
            user_input = Prompt.ask(
                prompt_config["prompt"],
                default=default_value,
                show_default=bool(default_value),
            )
            config[key] = user_input if user_input else None

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


def configure_boot_partition(  # noqa: C901
    device: str,
    config: dict[str, Any],
    pi_version: str,
) -> None:
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

        # Enable SPI for ePaper HAT
        if config.get("enable_spi"):
            # Uncomment dtparam=spi=on in config.txt (or add if missing)
            config_txt_path = boot_mount / "config.txt"
            result = subprocess.run(
                ["sudo", "cat", str(config_txt_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            config_content = result.stdout

            # Check if line exists (commented or uncommented)
            if "dtparam=spi=on" in config_content:
                # Uncomment if commented
                config_content = config_content.replace("#dtparam=spi=on", "dtparam=spi=on")
            else:
                # Add if missing
                config_content += "\n# Enable SPI for ePaper HAT\ndtparam=spi=on\n"

            temp_config = Path("/tmp/birdnetpi_config_txt")
            temp_config.write_text(config_content)
            subprocess.run(
                ["sudo", "cp", str(temp_config), str(config_txt_path)],
                check=True,
            )
            temp_config.unlink()
            console.print("[green]✓ SPI enabled for ePaper HAT[/green]")

            # Clone Waveshare ePaper library to boot partition for offline installation
            console.print()
            waveshare_dest = boot_mount / "waveshare-epd"
            temp_waveshare = Path("/tmp/waveshare_clone")

            # Remove old temp clone if it exists
            if temp_waveshare.exists():
                shutil.rmtree(temp_waveshare)

            # Clone only the Python subdirectory using sparse-checkout (~45MB vs full repo)
            # This is small enough to fit on the boot partition
            with console.status(
                "[cyan]Downloading Waveshare ePaper library "
                "(Python subdirectory, ~6MB transfer)...[/cyan]"
            ):
                # Initialize sparse checkout
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        "--filter=blob:none",
                        "--no-checkout",
                        "--quiet",
                        "https://github.com/waveshareteam/e-Paper.git",
                        str(temp_waveshare),
                    ],
                    check=True,
                )

                # Configure sparse checkout for Python subdirectory only
                subprocess.run(
                    ["git", "-C", str(temp_waveshare), "sparse-checkout", "init", "--cone"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(temp_waveshare),
                        "sparse-checkout",
                        "set",
                        "RaspberryPi_JetsonNano/python",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["git", "-C", str(temp_waveshare), "checkout", "--quiet"],
                    check=True,
                )

                # Copy only the Python subdirectory to boot partition
                python_dir = temp_waveshare / "RaspberryPi_JetsonNano" / "python"
                subprocess.run(
                    ["sudo", "cp", "-r", str(python_dir), str(waveshare_dest)],
                    check=True,
                )
                shutil.rmtree(temp_waveshare)
            console.print("[green]✓ Waveshare ePaper library downloaded to boot partition[/green]")

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

        # Copy LibreComputer portability script for Le Potato (Raspbian only, not Armbian)
        if pi_version == "Le Potato (Raspbian)":
            console.print()
            console.print("[cyan]Installing LibreComputer Raspbian Portability Script...[/cyan]")

            # Clone the portability repo to boot partition
            lrp_dest = boot_mount / "lrp"
            temp_clone = Path("/tmp/lrp_clone")

            # Remove any existing temp directory
            if temp_clone.exists():
                subprocess.run(["rm", "-rf", str(temp_clone)], check=True)

            # Clone the repo
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "https://github.com/libre-computer-project/libretech-raspbian-portability.git",
                    str(temp_clone),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Patch oneshot.sh to support Raspbian 12 (Bookworm) in addition to 11 (Bullseye)
            oneshot_path = temp_clone / "oneshot.sh"
            if oneshot_path.exists():
                oneshot_content = oneshot_path.read_text()
                # Change the version check from "11" only to "11" or "12"
                # The bash script uses '"11"' which in Python needs to be written as \'"11"\'
                old_check = 'elif [ "${TARGET_OS_RELEASE[VERSION_ID]}" != \'"11"\' ]; then'
                new_check = (
                    'elif [ "${TARGET_OS_RELEASE[VERSION_ID]}" != \'"11"\' ] && '
                    '[ "${TARGET_OS_RELEASE[VERSION_ID]}" != \'"12"\' ]; then'
                )
                if old_check in oneshot_content:
                    oneshot_content = oneshot_content.replace(old_check, new_check)
                    oneshot_content = oneshot_content.replace(
                        "only Raspbian 11 is supported",
                        "only Raspbian 11 and 12 are supported",
                    )

                    # Add LibreComputer keyring installation at the beginning
                    # This fixes expired GPG key issues - official solution from:
                    # https://hub.libre.computer/t/signatures-were-invalid-expkeysig-2e5fb7fc58c58ffb/4166
                    keyring_fix = """
# Install updated LibreComputer keyring to fix expired GPG keys
echo "Waiting for network to be ready..."
for i in $(seq 1 30); do
    if ping -c 1 -W 2 deb.libre.computer >/dev/null 2>&1; then
        echo "Network ready"
        break
    fi
    sleep 1
done

echo "Installing updated LibreComputer keyring..."
KEYRING_URL="https://deb.libre.computer/repo/pool/main/libr/libretech-keyring"
KEYRING_DEB="libretech-keyring_2024.05.19_all.deb"
if wget --no-check-certificate --timeout=30 --tries=3 \
    "$KEYRING_URL/$KEYRING_DEB" -O /tmp/libretech-keyring.deb; then
    # Verify downloaded file is a valid .deb package
    if file /tmp/libretech-keyring.deb | grep -q "Debian binary package"; then
        if dpkg -i /tmp/libretech-keyring.deb; then
            echo "✓ LibreComputer keyring updated successfully"
        else
            echo "⚠ Warning: Failed to install keyring package, continuing anyway..."
        fi
    else
        echo "⚠ Warning: Downloaded file is not a valid .deb package, skipping..."
    fi
    rm -f /tmp/libretech-keyring.deb
else
    echo "⚠ Warning: Failed to download keyring package, continuing anyway..."
fi

"""
                    # Insert after the shebang line
                    lines = oneshot_content.split("\n")
                    # Find first non-comment, non-empty line after shebang
                    insert_index = 1
                    for i, line in enumerate(lines[1:], 1):
                        if line.strip() and not line.strip().startswith("#"):
                            insert_index = i
                            break
                    lines.insert(insert_index, keyring_fix)
                    oneshot_content = "\n".join(lines)

                    # Comment out the wget that downloads the old expired GPG key
                    # The keyring package we installed above has the updated keys
                    import re

                    oneshot_content = re.sub(
                        r"^(wget\s+.*libre-computer-deb\.gpg.*)$",
                        r"# \1  # Commented: using updated keyring package instead",
                        oneshot_content,
                        flags=re.MULTILINE,
                    )

                    # Make grub-install non-fatal (Le Potato uses u-boot, not grub)
                    # The script tries to run grub-install for x86 boards,
                    # but Le Potato doesn't need it
                    oneshot_content = re.sub(
                        r"^(\$grub_install_cmd)$",
                        r"\1 || true  # Non-fatal: Le Potato uses u-boot, not grub",
                        oneshot_content,
                        flags=re.MULTILINE,
                    )

                    oneshot_path.write_text(oneshot_content)
                    console.print(
                        "[green]✓ Patched oneshot.sh to support Raspbian 12 (Bookworm)[/green]"
                    )
                else:
                    console.print("[yellow]Warning: Could not find version check to patch[/yellow]")

            # Copy to boot partition
            subprocess.run(
                ["sudo", "cp", "-r", str(temp_clone), str(lrp_dest)],
                check=True,
            )

            # Clean up temp directory
            subprocess.run(["rm", "-rf", str(temp_clone)], check=True)

            # Create helper script that runs portability script with correct model
            helper_script = """#!/bin/bash
# LibreComputer Le Potato Portability Helper Script
# This script automatically runs the portability script with the correct model number

set -e

echo "========================================="
echo "LibreComputer Le Potato Portability Setup"
echo "========================================="
echo ""
echo "This will convert this Raspbian SD card to boot on the Le Potato (AML-S905X-CC)."
echo ""
echo "WARNING: This will modify the bootloader and kernel on this SD card."
echo "After this process completes, the SD card will ONLY work on Le Potato,"
echo "not on Raspberry Pi anymore."
echo ""
read -r -p "Press Enter to continue, or Ctrl+C to cancel..."
echo ""

# Run the portability script with the Le Potato model number
sudo /boot/firmware/lrp/oneshot.sh aml-s905x-cc

echo ""
echo "Conversion complete! System will shut down."
echo "After shutdown, move the SD card to your Le Potato and boot it."
"""
            temp_helper = Path("/tmp/lepotato_setup.sh")
            temp_helper.write_text(helper_script)
            subprocess.run(
                ["sudo", "cp", str(temp_helper), str(boot_mount / "lepotato_setup.sh")],
                check=True,
            )
            # Make executable
            subprocess.run(
                ["sudo", "chmod", "+x", str(boot_mount / "lepotato_setup.sh")],
                check=True,
            )
            temp_helper.unlink()

            # Create README for user
            readme_content = """# LibreComputer Le Potato Setup Instructions

This SD card contains the Raspbian Portability Script for Le Potato.

## IMPORTANT: Two-Step Boot Process Required

1. **First boot on a Raspberry Pi:**
   - Insert this SD card into a Raspberry Pi (any model)
   - Boot the Pi and log in with the credentials you configured
   - Run the helper script: bash /boot/firmware/lepotato_setup.sh
   - The Pi will shut down when complete

2. **Move to Le Potato:**
   - Remove the SD card from the Raspberry Pi
   - Insert it into your Le Potato
   - Power on the Le Potato - it will now boot successfully!

3. **Install BirdNET-Pi:**
   - SSH into the Le Potato
   - Run: bash /boot/firmware/install.sh

## Helper Script

The lepotato_setup.sh script automatically runs the portability conversion
with the correct model number (aml-s905x-cc). You can also run the portability
script directly if needed:

    sudo /boot/firmware/lrp/oneshot.sh aml-s905x-cc

## Why This Is Necessary

The Le Potato (AML-S905X-CC) requires a modified bootloader and kernel to run
Raspbian. The portability script must run on a real Raspberry Pi to install
these components before the SD card will boot on the Le Potato.

For more information, visit:
https://github.com/libre-computer-project/libretech-raspbian-portability
"""
            temp_readme = Path("/tmp/birdnetpi_lepotato_readme.txt")
            temp_readme.write_text(readme_content)
            subprocess.run(
                ["sudo", "cp", str(temp_readme), str(boot_mount / "LE_POTATO_README.txt")],
                check=True,
            )
            temp_readme.unlink()

            console.print("[green]✓ LibreComputer portability script installed[/green]")
            console.print("[green]✓ Le Potato helper script: lepotato_setup.sh[/green]")
            console.print("[green]✓ Setup instructions: LE_POTATO_README.txt[/green]")

        # Create BirdNET-Pi pre-configuration file if any settings provided
        birdnet_config_lines = ["# BirdNET-Pi boot configuration"]
        has_birdnet_config = False

        if config.get("birdnet_device_name"):
            birdnet_config_lines.append(f"device_name={config['birdnet_device_name']}")
            has_birdnet_config = True

        if config.get("birdnet_latitude"):
            birdnet_config_lines.append(f"latitude={config['birdnet_latitude']}")
            has_birdnet_config = True

        if config.get("birdnet_longitude"):
            birdnet_config_lines.append(f"longitude={config['birdnet_longitude']}")
            has_birdnet_config = True

        if config.get("birdnet_timezone"):
            birdnet_config_lines.append(f"timezone={config['birdnet_timezone']}")
            has_birdnet_config = True

        if config.get("birdnet_language"):
            birdnet_config_lines.append(f"language={config['birdnet_language']}")
            has_birdnet_config = True

        if has_birdnet_config:
            temp_birdnet_config = Path("/tmp/birdnetpi_config.txt")
            temp_birdnet_config.write_text("\n".join(birdnet_config_lines) + "\n")
            subprocess.run(
                ["sudo", "cp", str(temp_birdnet_config), str(boot_mount / "birdnetpi_config.txt")],
                check=True,
            )
            temp_birdnet_config.unlink()
            console.print("[green]✓ BirdNET-Pi configuration written to boot partition[/green]")

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
@click.option(
    "--device-index",
    type=int,
    help="SD card device index (1-based) for unattended operation",
)
@click.option(
    "--device-type",
    type=str,
    help="Device type override (e.g., 'Pi 4', 'Le Potato (Armbian)')",
)
def main(save_config_flag: bool, device_index: int | None, device_type: str | None) -> None:
    """Flash Raspberry Pi OS to SD card and configure for BirdNET-Pi."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]BirdNET-Pi SD Card Flasher[/bold cyan]\n"
            "[dim]Create bootable Raspberry Pi OS SD cards configured for BirdNET-Pi[/dim]",
            border_style="cyan",
        )
    )

    # Try to select from saved profiles first
    profile_config, profile_name, edit_mode = select_profile()

    # Store which profile was selected (None for new config)
    saved_config = profile_config

    # Select device
    device = select_device(device_index=device_index)

    # Select Pi version
    pi_version = select_pi_version(
        saved_device_type=saved_config.get("device_type") if saved_config else None,
        device_type_override=device_type,
        edit_mode=edit_mode,
    )

    # Download image
    download_dir = Path.home() / ".cache" / "birdnetpi" / "images"
    download_dir.mkdir(parents=True, exist_ok=True)
    image_path = download_image(pi_version, download_dir)

    # Get configuration (edit_mode shows prompts with defaults instead of auto-using saved values)
    config = get_config_from_prompts(saved_config, edit_mode=edit_mode)

    # Add device_type to config before saving
    config["device_type"] = pi_version

    # Save configuration as profile
    # CRITICAL FIX: When editing, default to the original profile name, not "default"
    if (
        save_config_flag
        or edit_mode
        or (not saved_config and Confirm.ask("Save this configuration as a profile?"))
    ):
        default_name = profile_name if profile_name else "default"
        new_profile_name = Prompt.ask("Profile name", default=default_name)
        save_profile(new_profile_name, config)

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

    # Configure boot partition (skip for Armbian - uses different partition layout)
    image_info = PI_IMAGES[pi_version]
    is_armbian = image_info.get("is_armbian", False)
    if not is_armbian:
        configure_boot_partition(device, config, pi_version)
    else:
        console.print()
        console.print("[yellow]Note: Armbian uses its own first-boot configuration wizard[/yellow]")
        console.print(
            "[dim]You will be prompted to create a user and set up SSH on first boot[/dim]"
        )

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
        f"Device Model: [yellow]{pi_version}[/yellow]",
        f"Hostname: [cyan]{config.get('hostname', 'birdnetpi')}[/cyan]",
        f"Admin User: [cyan]{config['admin_user']}[/cyan]",
        "SSH: [green]Enabled[/green]",
    ]

    # Add WiFi status
    if config.get("enable_wifi"):
        summary_parts.append(f"WiFi: [green]Configured ({config['wifi_ssid']})[/green]")
    else:
        summary_parts.append("WiFi: [yellow]Not configured (Ethernet required)[/yellow]")

    # Special instructions for Le Potato (Raspbian)
    if pi_version == "Le Potato (Raspbian)":
        summary_parts.append("Portability Script: [green]Installed[/green]\n")
        summary_parts.append(
            "[bold yellow]⚠ IMPORTANT: Two-Step Boot Process Required![/bold yellow]\n"
        )
        summary_parts.append(
            "[dim]1. Boot this SD card in a Raspberry Pi (any model)\n"
            "2. Run: [cyan]bash /boot/firmware/lepotato_setup.sh[/cyan]\n"
            "3. Wait for Pi to shut down\n"
            "4. Move SD card to Le Potato and boot\n"
            "5. SSH in and run: [cyan]bash /boot/firmware/install.sh[/cyan]\n\n"
            "See [cyan]LE_POTATO_README.txt[/cyan] on boot partition for details.[/dim]"
        )
    # Direct boot instructions for Le Potato (Armbian)
    elif pi_version == "Le Potato (Armbian)":
        summary_parts.append("Native Armbian: [green]Direct boot ready[/green]\n")
        summary_parts.append(
            "[dim]Insert the SD card into your Le Potato and power it on.\n"
            "Armbian will run its first-boot setup wizard:\n"
            "  1. Create a root password\n"
            "  2. Create a user account\n"
            "  3. Configure locale/timezone\n\n"
            "After setup, SSH in and run the BirdNET-Pi installer:\n"
            "  [cyan]curl -fsSL https://raw.githubusercontent.com/mverteuil/BirdNET-Pi/"
            "main/install/install.sh | bash[/cyan][/dim]"
        )
    # Add installer script status for regular Pi
    elif config.get("copy_installer"):
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
