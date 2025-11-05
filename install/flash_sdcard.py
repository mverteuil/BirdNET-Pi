#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "click>=8.1.0",
#     "rich>=13.0.0",
#     "requests>=2.31.0",
#     "textual>=0.47.0",
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
from collections import OrderedDict
from pathlib import Path
from typing import Any

import click  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]

# Import TUI module
from flasher_tui import FlasherWizardApp
from rich.console import Console  # type: ignore[import-untyped]
from rich.panel import Panel  # type: ignore[import-untyped]
from rich.progress import (  # type: ignore[import-untyped]
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Prompt  # type: ignore[import-untyped]
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


# OS Properties
# Defines intrinsic capabilities of each operating system
OS_PROPERTIES = {
    "raspbian": {
        "wifi_config_method": "networkmanager",  # firstrun.sh uses NetworkManager
        "user_config_method": "userconf",  # userconf.txt
        "spi_config_method": "config_txt",  # config.txt dtparam=spi=on
        "install_sh_path": "/boot/firmware/install.sh",
        "install_sh_needs_preservation": False,  # Boot partition persists
    },
    "armbian": {
        "wifi_config_method": "netplan",  # systemd-networkd on minimal images
        "user_config_method": "not_logged_in_yet",  # .not_logged_in_yet file
        "spi_config_method": None,  # TODO: research Armbian SPI
        "install_sh_path": "/boot/install.sh",
        "install_sh_needs_preservation": False,  # ext4 partition persists
    },
    "dietpi": {
        "wifi_config_method": "dietpi_wifi",  # dietpi-wifi.txt
        "user_config_method": "root_only",  # Only root password via AUTO_SETUP_GLOBAL_PASSWORD
        "spi_config_method": "config_txt_device_dependent",  # config.txt for RPi, overlays for SBCs
        "install_sh_path": "/root/install.sh",
        "install_sh_needs_preservation": True,  # DIETPISETUP partition deleted after first boot
    },
}

# Device Properties
# Defines intrinsic hardware capabilities of each device
DEVICE_PROPERTIES = {
    "pi_zero_2w": {
        "has_wifi": True,
        "has_spi": True,
    },
    "pi_3": {
        "has_wifi": True,
        "has_spi": True,
    },
    "pi_4": {
        "has_wifi": True,
        "has_spi": True,
    },
    "pi_5": {
        "has_wifi": True,
        "has_spi": True,
    },
    "le_potato": {
        "has_wifi": False,  # No WiFi hardware
        "has_spi": True,  # GPIO header supports SPI
    },
    "orange_pi_0w2": {
        "has_wifi": True,  # Built-in WiFi
        "has_spi": True,  # Allwinner H618 supports SPI
    },
    "orange_pi_5_plus": {
        "has_wifi": True,  # Built-in WiFi
        "has_spi": True,  # RK3588 supports SPI
    },
    "orange_pi_5_pro": {
        "has_wifi": True,  # Built-in WiFi
        "has_spi": True,  # RK3588 supports SPI
    },
    "rock_5b": {
        "has_wifi": True,  # M.2 WiFi module support
        "has_spi": True,  # RK3588 supports SPI
    },
}


def get_combined_capabilities(os_key: str, device_key: str) -> dict[str, Any]:
    """Calculate combined capabilities from OS and device properties.

    Args:
        os_key: OS type (e.g., "raspbian", "armbian", "dietpi")
        device_key: Device key (e.g., "pi_4", "orangepi5")

    Returns:
        Dictionary of combined capabilities
    """
    os_props = OS_PROPERTIES.get(os_key, {})
    device_props = DEVICE_PROPERTIES.get(device_key, {})

    return {
        # WiFi is supported if OS can configure it AND device has hardware
        "supports_wifi": (
            os_props.get("wifi_config_method") is not None and device_props.get("has_wifi", False)
        ),
        # Custom user supported if OS has a method other than root_only
        "supports_custom_user": os_props.get("user_config_method") not in [None, "root_only"],
        # SPI supported if OS can configure it AND device has hardware
        "supports_spi": (
            os_props.get("spi_config_method") is not None and device_props.get("has_spi", False)
        ),
        # Pass through OS-specific properties
        "install_sh_path": os_props.get("install_sh_path", "/boot/install.sh"),
        "install_sh_needs_preservation": os_props.get("install_sh_needs_preservation", False),
        "wifi_config_method": os_props.get("wifi_config_method"),
        "user_config_method": os_props.get("user_config_method"),
        "spi_config_method": os_props.get("spi_config_method"),
    }


def copy_installer_script(
    boot_mount: Path,
    config: dict[str, Any],
    os_key: str,
    device_key: str,
) -> Path | None:
    """Copy install.sh to boot partition with OS-specific handling.

    Args:
        boot_mount: Path to mounted boot partition
        config: Configuration dictionary with copy_installer flag
        os_key: OS type for capability lookup
        device_key: Device key for capability lookup

    Returns:
        Path to the modified install.sh temp file, or None if not copied
    """
    caps = get_combined_capabilities(os_key, device_key)

    # For OSes that need preservation (DietPi), always copy the installer
    # because the boot partition will be deleted after first boot
    needs_preservation = caps.get("install_sh_needs_preservation", False)

    console.print(f"[cyan]DEBUG: os={os_key}, device={device_key}[/cyan]")
    copy_inst = config.get("copy_installer")
    console.print(f"[cyan]DEBUG: copy_installer={copy_inst}, preserve={needs_preservation}[/cyan]")

    if not copy_inst and not needs_preservation:
        console.print("[yellow]DEBUG: Skipping (not needed)[/yellow]")
        return None

    install_script = Path(__file__).parent / "install.sh"
    if not install_script.exists():
        console.print("[yellow]Warning: install.sh not found, skipping copy[/yellow]")
        return None

    # Read install.sh and substitute repo/branch defaults if configured
    install_content = install_script.read_text()

    # Debug: show what's in config
    console.print(f"[cyan]DEBUG: config keys = {list(config.keys())}[/cyan]")
    console.print(f"[cyan]DEBUG: birdnet_branch = {config.get('birdnet_branch')}[/cyan]")
    console.print(f"[cyan]DEBUG: birdnet_repo_url = {config.get('birdnet_repo_url')}[/cyan]")

    # Replace REPO_URL default if custom repo configured
    if config.get("birdnet_repo_url"):
        repo_url = config["birdnet_repo_url"]
        install_content = install_content.replace(
            'REPO_URL="${BIRDNETPI_REPO_URL:-https://github.com/mverteuil/BirdNET-Pi.git}"',
            f'REPO_URL="${{BIRDNETPI_REPO_URL:-{repo_url}}}"',
        )

    # Replace BRANCH default if custom branch configured
    if config.get("birdnet_branch"):
        branch = config["birdnet_branch"]
        install_content = install_content.replace(
            'BRANCH="${BIRDNETPI_BRANCH:-main}"', f'BRANCH="${{BIRDNETPI_BRANCH:-{branch}}}"'
        )

    # Write modified install.sh to temporary location, then copy to boot
    temp_install = Path("/tmp/install.sh")
    temp_install.write_text(install_content)

    install_dest = boot_mount / "install.sh"
    subprocess.run(["sudo", "cp", str(temp_install), str(install_dest)], check=True)
    subprocess.run(["sudo", "chmod", "+x", str(install_dest)], check=True)

    # For OSes that need preservation (DietPi), create wrapper script
    if caps.get("install_sh_needs_preservation"):
        final_path = caps.get("install_sh_path", "/root/install.sh")
        preserve_script_content = f"""#!/bin/bash
# Preserve and execute install.sh before/after DIETPISETUP partition is deleted
# This script runs during DietPi first boot automation

LOGFILE="/var/log/birdnetpi_preserve.log"
exec >> "$LOGFILE" 2>&1

echo "=== BirdNET-Pi Installer Preservation Script ==="
echo "Started at: $(date)"
echo "Running as: $(whoami)"
echo "Working directory: $(pwd)"

# Debug: Show what's mounted
echo ""
echo "=== Mounted filesystems ==="
mount | grep -E '/boot|/root'

# Debug: Show what's in /boot locations
echo ""
echo "=== /boot/firmware contents ==="
ls -la /boot/firmware/ 2>&1 || echo "/boot/firmware does not exist"

echo ""
echo "=== /boot contents ==="
ls -la /boot/ 2>&1 || echo "/boot does not exist"

# Try /boot/firmware first (Raspberry Pi), then /boot (other boards)
if [ -f /boot/firmware/install.sh ]; then
    echo ""
    echo "Found install.sh at /boot/firmware/install.sh"
    cp /boot/firmware/install.sh {final_path}
    chmod +x {final_path}
    echo "Preserved install.sh from /boot/firmware/ to {final_path}"
elif [ -f /boot/install.sh ]; then
    echo ""
    echo "Found install.sh at /boot/install.sh"
    cp /boot/install.sh {final_path}
    chmod +x {final_path}
    echo "Preserved install.sh from /boot/ to {final_path}"
else
    echo ""
    echo "ERROR: Could not find install.sh in /boot/firmware/ or /boot/"
    echo "Skipping installation - install.sh must be run manually"
    exit 0  # Don't fail DietPi automation, just skip
fi

if [ -f /boot/firmware/birdnetpi_config.json ]; then
    cp /boot/firmware/birdnetpi_config.json /root/birdnetpi_config.json
    echo "Preserved birdnetpi_config.json from /boot/firmware/ to /root/"
elif [ -f /boot/birdnetpi_config.json ]; then
    cp /boot/birdnetpi_config.json /root/birdnetpi_config.json
    echo "Preserved birdnetpi_config.json from /boot/ to /root/"
fi

# Verify preservation was successful
if [ ! -f {final_path} ]; then
    echo ""
    echo "ERROR: Failed to preserve install.sh to {final_path}"
    echo "Installation must be run manually"
    exit 0  # Don't fail DietPi automation
fi

echo ""
echo "Successfully preserved install.sh to {final_path}"
echo "Installation will NOT run automatically - run manually with:"
echo "  sudo bash {final_path}"
echo ""
echo "Preservation complete at: $(date)"
echo "Log saved to: $LOGFILE"

# NOTE: We do NOT execute install.sh automatically anymore
# Users should run it manually after first boot to have control
exit 0
"""
        preserve_script_path = boot_mount / "preserve_installer.sh"
        temp_preserve = Path("/tmp/preserve_installer.sh")
        temp_preserve.write_text(preserve_script_content)
        subprocess.run(["sudo", "cp", str(temp_preserve), str(preserve_script_path)], check=True)
        subprocess.run(["sudo", "chmod", "+x", str(preserve_script_path)], check=True)
        temp_preserve.unlink()

        # ALSO create DietPi-Automation pre-script (runs BEFORE partition cleanup)
        # This is critical because DIETPISETUP partition gets deleted after first boot
        # Automation_Custom_PreScript.sh runs BEFORE the cleanup
        automation_script_content = f"""#!/bin/bash
# DietPi Pre-Automation Script - runs BEFORE DIETPISETUP partition deletion
# This preserves install.sh from /boot BEFORE it gets deleted

LOGFILE="/var/log/birdnetpi_automation.log"
exec >> "$LOGFILE" 2>&1

echo "=== BirdNET-Pi DietPi Pre-Automation Script ==="
echo "Started at: $(date)"
echo "Running as: $(whoami)"
echo "PWD: $(pwd)"

# Show what boot partitions exist
echo ""
echo "=== Available boot partitions ==="
mount | grep -E "/boot"
echo ""

# Try to preserve install.sh from boot partition
# On Orange Pi 5 Pro and similar, DIETPISETUP is at /boot (not /boot/firmware)
if [ -f /boot/install.sh ]; then
    echo "Found install.sh at /boot/install.sh"
    cp -v /boot/install.sh {final_path}
    chmod +x {final_path}
    echo "Preserved install.sh to {final_path}"
elif [ -f /boot/firmware/install.sh ]; then
    echo "Found install.sh at /boot/firmware/install.sh"
    cp -v /boot/firmware/install.sh {final_path}
    chmod +x {final_path}
    echo "Preserved install.sh to {final_path}"
else
    echo "ERROR: Could not find install.sh in /boot or /boot/firmware"
    echo ""
    echo "=== /boot contents ==="
    ls -la /boot/ 2>&1 || echo "/boot not accessible"
    echo ""
    echo "=== /boot/firmware contents ==="
    ls -la /boot/firmware/ 2>&1 || echo "/boot/firmware not accessible"
    exit 1
fi

# Also preserve config if present
if [ -f /boot/birdnetpi_config.json ]; then
    cp -v /boot/birdnetpi_config.json /root/birdnetpi_config.json
    echo "Preserved birdnetpi_config.json from /boot"
elif [ -f /boot/firmware/birdnetpi_config.json ]; then
    cp -v /boot/firmware/birdnetpi_config.json /root/birdnetpi_config.json
    echo "Preserved birdnetpi_config.json from /boot/firmware"
fi

# Verify preservation
if [ -f {final_path} ]; then
    echo ""
    echo "SUCCESS: install.sh preserved to {final_path}"
    ls -lh {final_path}
    echo ""
    echo "================================================"
    echo "BirdNET-Pi installer is ready!"
    echo "After first boot, run: sudo bash {final_path}"
    echo "================================================"
else
    echo ""
    echo "FAILURE: Could not preserve install.sh"
    exit 1
fi

echo ""
echo "Pre-automation script completed at: $(date)"
echo "Log saved to: $LOGFILE"
exit 0
"""
        # Create BOTH PreScript (runs before cleanup) and regular Script (runs after)
        # PreScript is what we need, but we'll create both for maximum compatibility
        prescript_path = boot_mount / "Automation_Custom_PreScript.sh"
        script_path = boot_mount / "Automation_Custom_Script.sh"

        temp_automation = Path("/tmp/Automation_Custom_PreScript.sh")
        temp_automation.write_text(automation_script_content)
        subprocess.run(["sudo", "cp", str(temp_automation), str(prescript_path)], check=True)
        subprocess.run(["sudo", "chmod", "+x", str(prescript_path)], check=True)

        # Also copy as regular script for backwards compatibility
        subprocess.run(["sudo", "cp", str(temp_automation), str(script_path)], check=True)
        subprocess.run(["sudo", "chmod", "+x", str(script_path)], check=True)
        temp_automation.unlink()

        # Create README with installation instructions
        readme_content = f"""BirdNET-Pi Installation Instructions for DietPi
===============================================

Your SD card has been configured for BirdNET-Pi installation!

AFTER FIRST BOOT:
-----------------
1. SSH into your device
2. Check if install.sh was preserved:

   ls -l {final_path}

3. If the file exists, run the installer:

   sudo bash {final_path}

TROUBLESHOOTING:
----------------
If {final_path} doesn't exist, check the preservation logs:

   cat /var/log/birdnetpi_preserve.log       # AUTO_SETUP_CUSTOM_SCRIPT_EXEC log
   cat /var/log/birdnetpi_automation.log     # Automation_Custom_Script.sh log

These logs show what happened during the preservation process.
At least one of these methods should work on your device.

MANUAL INSTALLATION:
--------------------
If preservation failed, you can still install BirdNET-Pi manually:

1. Clone the repository:
   git clone https://github.com/your-repo/BirdNET-Pi.git
   cd BirdNET-Pi

2. Run the installer:
   sudo bash install/install.sh

For more help, visit: https://github.com/your-repo/BirdNET-Pi
"""
        readme_path = boot_mount / "BIRDNETPI_README.txt"
        temp_readme = Path("/tmp/BIRDNETPI_README.txt")
        temp_readme.write_text(readme_content)
        subprocess.run(["sudo", "cp", str(temp_readme), str(readme_path)], check=True)
        temp_readme.unlink()

        console.print("[green]✓ Copied install.sh with triple preservation methods:[/green]")
        console.print("[dim]  - preserve_installer.sh (via AUTO_SETUP_CUSTOM_SCRIPT_EXEC)[/dim]")
        console.print(
            "[dim]  - Automation_Custom_PreScript.sh (runs BEFORE partition cleanup)[/dim]"
        )
        console.print("[dim]  - Automation_Custom_Script.sh (runs AFTER partition cleanup)[/dim]")
        console.print(f"[dim]  - Target location: {final_path}[/dim]")
        console.print("[green]✓ Created BIRDNETPI_README.txt on boot partition[/green]")
    else:
        final_path = caps.get("install_sh_path", "/boot/install.sh")
        console.print(f"[green]✓ Copied install.sh to {final_path}[/green]")

    # Return the temp file path so it can be used for rootfs copy
    return temp_install


def copy_birdnetpi_config(  # noqa: C901
    boot_mount: Path,
    config: dict[str, Any],
    os_key: str | None = None,
    device_key: str | None = None,
) -> Path | None:
    """Copy birdnetpi_config.json to boot partition for unattended install.sh.

    Args:
        boot_mount: Path to mounted boot partition
        config: Configuration dictionary with BirdNET-Pi settings
        os_key: Operating system key (e.g., "dietpi", "raspbian")
        device_key: Device key (e.g., "orange_pi_5_pro", "pi_5")

    Returns:
        Path to temporary config file if created, None otherwise
    """
    import json

    # Build JSON config from all available settings
    boot_config: dict[str, Any] = {}

    # OS and device information
    if os_key:
        boot_config["os"] = os_key
    if device_key:
        boot_config["device"] = device_key

    # Install-time settings
    if config.get("birdnet_repo_url"):
        boot_config["repo_url"] = config["birdnet_repo_url"]
    if config.get("birdnet_branch"):
        boot_config["branch"] = config["birdnet_branch"]

    # WiFi settings
    if config.get("wifi_ssid"):
        boot_config["wifi_ssid"] = config["wifi_ssid"]
    if config.get("wifi_password"):
        boot_config["wifi_password"] = config["wifi_password"]
    if config.get("wifi_auth"):
        boot_config["wifi_auth"] = config["wifi_auth"]

    # Application settings
    if config.get("birdnet_device_name"):
        boot_config["device_name"] = config["birdnet_device_name"]
    if config.get("birdnet_latitude"):
        boot_config["latitude"] = config["birdnet_latitude"]
    if config.get("birdnet_longitude"):
        boot_config["longitude"] = config["birdnet_longitude"]
    if config.get("birdnet_timezone"):
        boot_config["timezone"] = config["birdnet_timezone"]
    if config.get("birdnet_language"):
        boot_config["language"] = config["birdnet_language"]

    # Only write if we have at least one setting
    if boot_config:
        temp_config = Path("/tmp/birdnetpi_config.json")
        temp_config.write_text(json.dumps(boot_config, indent=2) + "\n")
        subprocess.run(
            ["sudo", "cp", str(temp_config), str(boot_mount / "birdnetpi_config.json")],
            check=True,
        )
        console.print("[green]✓ BirdNET-Pi configuration written to boot partition[/green]")
        return temp_config
    return None


# OS and device image URLs (Lite/Minimal versions for headless server)
# Organized by OS type, then by device
# Device ordering: 0-5 reserved for official Raspberry Pi models, then alphabetical
OS_IMAGES = {
    "raspbian": {
        "name": "Raspberry Pi OS",
        "devices": OrderedDict(
            [
                # Index 0: Pi Zero 2 W
                (
                    "pi_zero_2w",
                    {
                        "name": "Raspberry Pi Zero 2 W",
                        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",  # noqa: E501
                    },
                ),
                # Index 1: Reserved for Pi 1 (not supported - 32-bit only)
                # Index 2: Reserved for Pi 2 (not supported - 32-bit only)
                # Index 3: Pi 3
                (
                    "pi_3",
                    {
                        "name": "Raspberry Pi 3",
                        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",  # noqa: E501
                    },
                ),
                # Index 4: Pi 4
                (
                    "pi_4",
                    {
                        "name": "Raspberry Pi 4",
                        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",  # noqa: E501
                    },
                ),
                # Index 5: Pi 5
                (
                    "pi_5",
                    {
                        "name": "Raspberry Pi 5",
                        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",  # noqa: E501
                    },
                ),
                # Non-Pi devices in alphabetical order
                (
                    "le_potato",
                    {
                        "name": "Le Potato",
                        "url": "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                        "sha256": "3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",  # noqa: E501
                        "requires_portability": True,
                    },
                ),
            ]
        ),
    },
    "armbian": {
        "name": "Armbian",
        "devices": OrderedDict(
            [
                # Non-Pi devices in alphabetical order (no official Pi support)
                (
                    "le_potato",
                    {
                        "name": "Le Potato",
                        "url": "https://dl.armbian.com/lepotato/Bookworm_current_minimal",
                        "is_armbian": True,
                    },
                ),
                (
                    "orange_pi_0w2",
                    {
                        "name": "Orange Pi Zero 2W",
                        "url": "https://dl.armbian.com/orangepizero2w/Bookworm_current_minimal",
                        "is_armbian": True,
                    },
                ),
                (
                    "orange_pi_5_plus",
                    {
                        "name": "Orange Pi 5 Plus",
                        "url": "https://dl.armbian.com/orangepi5-plus/Bookworm_current_minimal",
                        "is_armbian": True,
                    },
                ),
                (
                    "orange_pi_5_pro",
                    {
                        "name": "Orange Pi 5 Pro",
                        "url": "https://dl.armbian.com/orangepi5pro/Trixie_vendor_minimal",
                        "is_armbian": True,
                    },
                ),
                (
                    "rock_5b",
                    {
                        "name": "Radxa ROCK 5B",
                        "url": "https://dl.armbian.com/rock-5b/Bookworm_current_minimal",
                        "is_armbian": True,
                    },
                ),
            ]
        ),
    },
    "dietpi": {
        "name": "DietPi",
        "devices": OrderedDict(
            [
                # Index 0: Pi Zero 2 W
                (
                    "pi_zero_2w",
                    {
                        "name": "Raspberry Pi Zero 2 W",
                        "url": "https://dietpi.com/downloads/images/DietPi_RPi234-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                # Index 1: Reserved for Pi 1 (not supported - 32-bit only)
                # Index 2: Reserved for Pi 2 (not supported - 32-bit only)
                # Index 3: Pi 3
                (
                    "pi_3",
                    {
                        "name": "Raspberry Pi 3",
                        "url": "https://dietpi.com/downloads/images/DietPi_RPi234-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                # Index 4: Pi 4
                (
                    "pi_4",
                    {
                        "name": "Raspberry Pi 4",
                        "url": "https://dietpi.com/downloads/images/DietPi_RPi234-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                # Index 5: Pi 5
                (
                    "pi_5",
                    {
                        "name": "Raspberry Pi 5",
                        "url": "https://dietpi.com/downloads/images/DietPi_RPi5-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                # Non-Pi devices in alphabetical order
                (
                    "orange_pi_0w2",
                    {
                        "name": "Orange Pi Zero 2W",
                        "url": "https://dietpi.com/downloads/images/DietPi_OrangePiZero2W-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                (
                    "orange_pi_5_plus",
                    {
                        "name": "Orange Pi 5 Plus",
                        "url": "https://dietpi.com/downloads/images/DietPi_OrangePi5Plus-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                (
                    "orange_pi_5_pro",
                    {
                        "name": "Orange Pi 5 Pro",
                        "url": "https://dietpi.com/downloads/images/DietPi_OrangePi5Pro-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
                (
                    "rock_5b",
                    {
                        "name": "Radxa ROCK 5B",
                        "url": "https://dietpi.com/downloads/images/DietPi_ROCK5B-ARMv8-Bookworm.img.xz",
                        "is_dietpi": True,
                    },
                ),
            ]
        ),
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
    """Select a block device to flash using TUI or command-line option.

    Args:
        device_index: Optional 1-based index to select device without TUI

    Returns:
        Selected device path (e.g., "/dev/disk2")
    """
    devices = list_block_devices()

    if not devices:
        console.print("[red]No removable devices found![/red]")
        sys.exit(1)

    # If device_index provided, validate and use it (no TUI)
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

        # Still need confirmation even with device_index
        confirm = Prompt.ask(
            f"\n[bold red]Are you sure you want to flash {selected['device']}? "
            "This will ERASE ALL DATA![/bold red]",
            choices=["yes", "no"],
            default="no",
        )
        if confirm != "yes":
            console.print("[yellow]Cancelled[/yellow]")
            sys.exit(0)

        return selected["device"]

    # Otherwise, use TUI for device selection
    from flasher_tui import DeviceSelectionApp

    app = DeviceSelectionApp(devices)
    selected_device = app.run()

    if selected_device is None:
        console.print("[yellow]Device selection cancelled[/yellow]")
        sys.exit(0)

    return selected_device["device"]


def download_image_new(os_key: str, device_key: str, download_dir: Path) -> Path:  # noqa: C901
    """Download OS image for the selected OS and device.

    Args:
        os_key: Selected OS key (e.g., "raspbian", "armbian", "dietpi")
        device_key: Selected device key (e.g., "pi_4", "orange_pi_5_pro")
        download_dir: Directory to store downloaded images

    Returns:
        Path to the downloaded image file
    """
    image_info = OS_IMAGES[os_key]["devices"][device_key]
    os_name = OS_IMAGES[os_key]["name"]
    device_name = image_info["name"]
    url = image_info["url"]
    is_armbian = image_info.get("is_armbian", False)
    is_dietpi = image_info.get("is_dietpi", False)

    # For Armbian/DietPi, follow redirects to get actual download URL
    if is_armbian or is_dietpi:
        os_label = "Armbian" if is_armbian else "DietPi"
        console.print(f"[cyan]Resolving {os_label} image URL for {device_name}...[/cyan]")
        # HEAD request to follow redirects and get actual filename
        head_response = requests.head(url, allow_redirects=True, timeout=30)
        head_response.raise_for_status()

        # Extract final URL and filename after redirect
        final_url = head_response.url
        url = final_url  # Use the actual file URL for download

        # Try to get filename from Content-Disposition header
        filename = None
        content_disp = head_response.headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            # Extract filename from Content-Disposition header
            import re

            match = re.search(r'filename[*]?=(?:"([^"]+)"|([^\s;]+))', content_disp)
            if match:
                filename = match.group(1) or match.group(2)
                # Clean up any URL encoding
                from urllib.parse import unquote

                filename = unquote(filename)

        # Fallback: extract from URL query parameter or path
        if not filename:
            if "filename=" in final_url:
                # Try to extract from response-content-disposition query param
                import re
                from urllib.parse import unquote

                match = re.search(r"filename%3D([^&]+)", final_url)
                if match:
                    filename = unquote(match.group(1))
            else:
                # Last resort: use last path component (may be too long)
                filename = final_url.split("/")[-1].split("?")[0]

        # If filename is still too long or invalid, create a safe one
        if not filename or len(filename) > 200:
            # Use device-specific name
            filename = f"{os_label.lower()}_{device_key}.img.xz"

        console.print(f"[dim]Resolved to: {filename}[/dim]")
    else:
        filename = url.split("/")[-1]

    filepath = download_dir / filename

    if filepath.exists():
        console.print(f"[green]Using cached image: {filepath}[/green]")
        return filepath

    console.print(f"[cyan]Downloading {os_name} image for {device_name}...[/cyan]")

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

            # Parse SHA file - handle different formats
            sha_content = sha_response.text.strip()

            # Check if this looks like binary data (not a text SHA file)
            if not sha_content.isprintable() or len(sha_content) < 64:
                raise ValueError("SHA file does not contain valid text")

            # Try to extract hash - handle formats like:
            # "hash filename" or just "hash"
            parts = sha_content.split()
            if parts:
                expected_sha = parts[0]
                # Validate it looks like a hex hash (64 chars for SHA256)
                if not (
                    len(expected_sha) == 64
                    and all(c in "0123456789abcdefABCDEF" for c in expected_sha)
                ):
                    raise ValueError(f"Invalid SHA256 hash format: {expected_sha[:20]}...")
            else:
                raise ValueError("Could not extract hash from SHA file")

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


def configure_armbian_with_anylinuxfs(  # noqa: C901
    device: str,
    config: dict[str, Any],
    os_key: str,
    device_key: str,
) -> None:
    """Configure Armbian ext4 partition using anylinuxfs.

    Args:
        device: Device path (e.g., "/dev/disk4")
        config: Configuration dict with WiFi, user, password settings
        os_key: Operating system key (e.g., "armbian")
        device_key: Device key (e.g., "opi5pro")
    """
    console.print()
    console.print("[cyan]Configuring Armbian partition...[/cyan]")

    # Check if anylinuxfs is installed
    anylinuxfs_path = shutil.which("anylinuxfs")
    if not anylinuxfs_path:
        console.print("[yellow]anylinuxfs not found - skipping automated configuration[/yellow]")
        console.print(
            "[dim]Install anylinuxfs for automated setup: "
            "brew tap nohajc/anylinuxfs && brew install anylinuxfs[/dim]"
        )
        return

    # Mount the ext4 partition using anylinuxfs
    partition = f"{device}s1"  # First partition is root

    # Check if anylinuxfs already has something mounted
    console.print("[cyan]Checking for existing anylinuxfs mounts...[/cyan]")
    try:
        # Unmount any existing anylinuxfs mount (it can only mount one at a time)
        subprocess.run(
            ["sudo", "anylinuxfs", "unmount"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        time.sleep(2)  # Wait for unmount to complete
    except Exception:
        pass  # Ignore errors, continue anyway

    # Prevent macOS from trying to mount the ext4 partition
    # macOS will show "disk not readable" dialog otherwise
    console.print("[cyan]Preventing macOS auto-mount...[/cyan]")
    try:
        # Unmount any auto-mounted partitions from this disk
        subprocess.run(
            ["diskutil", "unmountDisk", device],
            capture_output=True,
            check=False,  # Don't fail if nothing was mounted
        )
    except Exception:
        pass  # Ignore errors, continue anyway

    try:
        console.print(f"[cyan]Mounting {partition} using anylinuxfs...[/cyan]")
        console.print("[dim]This may take 10-15 seconds to start the microVM...[/dim]")
        console.print("[yellow]You may be prompted for your password by anylinuxfs[/yellow]")
        console.print(
            "[yellow]If macOS shows 'disk not readable', "
            "click 'Ignore' - anylinuxfs will handle it[/yellow]"
        )

        # Run anylinuxfs - it will fork to background and exit with 0
        # We need to wait for the mount to appear after the command completes
        result = subprocess.run(
            ["sudo", "anylinuxfs", partition, "-w", "false"],
            capture_output=False,  # Allow password prompt to show
            check=False,
        )

        if result.returncode != 0:
            console.print(f"[red]anylinuxfs failed with exit code: {result.returncode}[/red]")
            return

        console.print("[dim]Waiting for mount to appear...[/dim]")

        # Wait for mount to appear by checking common mount points
        # anylinuxfs typically mounts to /Volumes/armbi_root or similar
        mount_point = None
        possible_mount_names = ["armbi_root", "armbian_root", "ARMBIAN"]

        for attempt in range(60):
            time.sleep(1)

            # Check for mount point in /Volumes
            try:
                volumes_path = Path("/Volumes")
                if volumes_path.exists():
                    for volume in volumes_path.iterdir():
                        volume_name = volume.name.lower()
                        # Check if this looks like an Armbian mount
                        if any(name.lower() in volume_name for name in possible_mount_names):
                            if volume.is_dir():
                                # Verify it's actually mounted by checking for Linux directories
                                if (volume / "etc").exists() or (volume / "boot").exists():
                                    mount_point = volume
                                    break
            except Exception as e:
                console.print(f"[dim]Error checking volumes: {e}[/dim]")
                pass  # Ignore errors, keep polling

            if mount_point:
                break

            if attempt % 5 == 0 and attempt > 0:
                console.print(f"[dim]Still waiting for mount... ({attempt}s)[/dim]")

        if not mount_point or not mount_point.exists():
            console.print("[red]Could not find anylinuxfs mount point after 60 seconds[/red]")
            console.print("[yellow]Check /Volumes for armbi_root or similar mount[/yellow]")
            return

        console.print(f"[green]✓ Mounted at {mount_point}[/green]")

        # Configure WiFi via armbian_first_run.txt
        if config.get("enable_wifi"):
            console.print("[cyan]Configuring WiFi...[/cyan]")
            boot_dir = mount_point / "boot"
            armbian_first_run = boot_dir / "armbian_first_run.txt"

            wifi_config = f"""#-----------------------------------------------------------------
# Armbian first run configuration
# Generated by BirdNET-Pi flash tool
#-----------------------------------------------------------------

FR_general_delete_this_file_after_completion=1

FR_net_change_defaults=1
FR_net_wifi_enabled=1
FR_net_wifi_ssid='{config["wifi_ssid"]}'
FR_net_wifi_key='{config["wifi_password"]}'
FR_net_wifi_countrycode='US'
FR_net_ethernet_enabled=0
"""
            # Write via temp file then copy with sudo
            # Use -X to skip extended attributes (NFS mounts don't support them)
            temp_wifi = Path("/tmp/armbian_first_run.txt")
            temp_wifi.write_text(wifi_config)
            subprocess.run(["sudo", "cp", "-X", str(temp_wifi), str(armbian_first_run)], check=True)
            temp_wifi.unlink()
            console.print(
                f"[green]✓ WiFi configured via armbian_first_run.txt "
                f"(SSID: {config['wifi_ssid']})[/green]"
            )

            # ALSO configure WiFi via netplan for systemd-networkd (minimal images)
            # This works on minimal images that don't have NetworkManager
            console.print("[cyan]Configuring WiFi via netplan...[/cyan]")
            netplan_dir = mount_point / "etc" / "netplan"
            netplan_wifi = netplan_dir / "30-wifis-dhcp.yaml"

            # Escape SSID and password for YAML
            wifi_ssid = config["wifi_ssid"].replace('"', '\\"')
            wifi_password = config["wifi_password"].replace('"', '\\"')

            netplan_config = f"""# Created by BirdNET-Pi flash tool
# WiFi configuration for systemd-networkd
network:
  wifis:
    wlan0:
      dhcp4: yes
      dhcp6: yes
      access-points:
        "{wifi_ssid}":
         password: "{wifi_password}"
"""
            # Write via temp file then copy with sudo
            temp_netplan = Path("/tmp/30-wifis-dhcp.yaml")
            temp_netplan.write_text(netplan_config)
            subprocess.run(["sudo", "cp", "-X", str(temp_netplan), str(netplan_wifi)], check=True)
            # Set proper permissions (netplan requires 600)
            subprocess.run(["sudo", "chmod", "600", str(netplan_wifi)], check=True)
            temp_netplan.unlink()
            console.print(
                f"[green]✓ WiFi configured via netplan (SSID: {config['wifi_ssid']})[/green]"
            )

        # Configure user and password via .not_logged_in_yet
        console.print("[cyan]Configuring user account...[/cyan]")
        root_dir = mount_point / "root"
        not_logged_in = root_dir / ".not_logged_in_yet"

        admin_user = config.get("admin_user", "birdnetpi")
        admin_password = config.get("admin_password", "birdnetpi")

        user_config = f"""# Armbian first boot user configuration
# Generated by BirdNET-Pi flash tool

PRESET_ROOT_PASSWORD="{admin_password}"
PRESET_USER_NAME="{admin_user}"
PRESET_USER_PASSWORD="{admin_password}"
PRESET_USER_SHELL="bash"
"""
        # Write via temp file then copy with sudo
        # Use -X to skip extended attributes (NFS mounts don't support them)
        temp_user = Path("/tmp/not_logged_in_yet")
        temp_user.write_text(user_config)
        subprocess.run(["sudo", "cp", "-X", str(temp_user), str(not_logged_in)], check=True)
        temp_user.unlink()
        console.print(f"[green]✓ User configured (username: {admin_user})[/green]")

        # Copy installer script if requested
        copy_installer_script(mount_point / "boot", config, os_key, device_key)

        # Copy BirdNET-Pi pre-configuration file if any settings provided
        copy_birdnetpi_config(mount_point / "boot", config)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error configuring Armbian: {e}[/red]")
        console.print("[yellow]Continuing without automated configuration[/yellow]")
    finally:
        # Unmount
        console.print("[cyan]Unmounting anylinuxfs...[/cyan]")
        try:
            subprocess.run(["sudo", "anylinuxfs", "unmount"], check=True, timeout=10)
            console.print("[green]✓ Armbian partition configured and unmounted[/green]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Warning: Unmount timed out - trying stop command[/yellow]")
            try:
                subprocess.run(["sudo", "anylinuxfs", "stop"], check=True, timeout=5)
            except Exception:
                console.print("[yellow]Warning: Could not stop anylinuxfs cleanly[/yellow]")
        except subprocess.CalledProcessError:
            console.print("[yellow]Warning: Could not unmount anylinuxfs[/yellow]")


def configure_dietpi_boot(  # noqa: C901
    device: str, config: dict[str, Any], os_key: str, device_key: str
) -> None:
    """Configure DietPi boot partition with dietpi.txt and dietpi-wifi.txt."""
    console.print()
    console.print("[cyan]Configuring DietPi boot partition...[/cyan]")

    # Initialize config_file to None (will be set by copy_birdnetpi_config if config exists)
    config_file: Path | None = None

    # Mount boot partition
    if platform.system() == "Darwin":
        # DietPi uses different partition numbers on different devices
        # Find the FAT partition that contains dietpi.txt
        boot_partition = None
        boot_mount = None

        # Check partitions 1-3 for a FAT filesystem with dietpi.txt
        for partition_num in range(1, 4):
            test_partition = f"{device}s{partition_num}"

            # Check if partition exists
            result = subprocess.run(
                ["diskutil", "info", test_partition],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                continue  # Partition doesn't exist

            # Check if it's a FAT filesystem (mountable by macOS)
            if "FAT" not in result.stdout:
                continue

            # Try to mount it
            subprocess.run(["diskutil", "mount", test_partition], check=False, capture_output=True)
            time.sleep(1)

            # Find where it mounted
            mount_info = subprocess.run(
                ["diskutil", "info", test_partition],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in mount_info.stdout.splitlines():
                if "Mount Point:" in line:
                    mount_path = line.split(":", 1)[1].strip()
                    if mount_path and mount_path != "Not applicable (no file system)":
                        test_mount = Path(mount_path)
                        # Check if dietpi.txt exists
                        if (test_mount / "dietpi.txt").exists():
                            boot_partition = test_partition
                            boot_mount = test_mount
                            break

            if boot_mount:
                break

        if not boot_mount:
            console.print("[red]Error: Could not find DietPi configuration partition[/red]")
            console.print("[yellow]Looking for FAT partition with dietpi.txt file[/yellow]")
            return
    else:
        boot_partition = f"{device}1"
        boot_mount = Path("/mnt/dietpi_boot")
        boot_mount.mkdir(parents=True, exist_ok=True)
        subprocess.run(["sudo", "mount", boot_partition, str(boot_mount)], check=True)

    try:
        console.print(f"[dim]Boot partition mounted at: {boot_mount}[/dim]")

        # Read existing dietpi.txt
        dietpi_txt_path = boot_mount / "dietpi.txt"
        if not dietpi_txt_path.exists():
            console.print("[yellow]Warning: dietpi.txt not found on boot partition[/yellow]")
            return

        # Read the file
        with open(dietpi_txt_path) as f:
            dietpi_txt_lines = f.readlines()

        # Update configuration values
        updates = {
            "AUTO_SETUP_AUTOMATED": "1",  # Enable automated first-run setup
            "AUTO_SETUP_INSTALL_SOFTWARE": "1",  # Required for Automation_Custom_Script.sh to run!
            "AUTO_SETUP_NET_HOSTNAME": config.get("hostname", "birdnetpi"),
            "AUTO_SETUP_GLOBAL_PASSWORD": config["admin_password"],
            "AUTO_SETUP_TIMEZONE": config.get("timezone", "UTC"),
            "AUTO_SETUP_LOCALE": "en_US.UTF-8",
            "AUTO_SETUP_KEYBOARD_LAYOUT": "us",  # Set keyboard layout
            "AUTO_SETUP_SSH_SERVER_INDEX": "-2",  # Enable OpenSSH (more reliable)
            "CONFIG_BOOT_WAIT_FOR_NETWORK": "2",  # Wait for network (required)
        }

        # Enable WiFi if configured
        if config.get("enable_wifi"):
            updates["AUTO_SETUP_NET_WIFI_ENABLED"] = "1"
            updates["AUTO_SETUP_NET_WIFI_COUNTRY_CODE"] = config.get("wifi_country", "US")

        # If install.sh will be copied, configure DietPi to preserve it
        # The DIETPISETUP partition (/boot or /boot/firmware) is deleted after first boot,
        # so we create a script that copies install.sh to /root during first boot
        preserve_installer = config.get("copy_installer")
        if preserve_installer:
            # Check if this is a Raspberry Pi (has config.txt in boot partition)
            # On RPi, DietPi uses /boot/firmware/, on other boards it's /boot/
            config_txt_path = boot_mount / "config.txt"
            if config_txt_path.exists():
                # Raspberry Pi - use /boot/firmware/
                updates["AUTO_SETUP_CUSTOM_SCRIPT_EXEC"] = "/boot/firmware/preserve_installer.sh"
            else:
                # Other boards - use /boot/
                updates["AUTO_SETUP_CUSTOM_SCRIPT_EXEC"] = "/boot/preserve_installer.sh"

        # Apply updates to dietpi.txt
        # Handle both uncommented lines and commented lines (starting with #)
        new_lines = []
        updated_keys = set()

        for line in dietpi_txt_lines:
            updated = False
            stripped_line = line.strip()

            for key, value in updates.items():
                # Match several patterns:
                # - KEY=value
                # - #KEY=value
                # - KEY =value (with space)
                # - # KEY=value (with space after #)
                if (
                    stripped_line.startswith(f"{key}=")
                    or stripped_line.startswith(f"#{key}=")
                    or stripped_line.startswith(f"{key} =")
                    or stripped_line.startswith(f"# {key}=")
                ):
                    new_lines.append(f"{key}={value}\n")
                    updated = True
                    updated_keys.add(key)
                    console.print(f"[dim]  Setting {key}={value}[/dim]")
                    break
            if not updated:
                new_lines.append(line)

        # Verify all keys were found and updated
        missing_keys = set(updates.keys()) - updated_keys
        if missing_keys:
            console.print(
                f"[yellow]Warning: Could not find these settings in dietpi.txt: "
                f"{missing_keys}[/yellow]"
            )
            console.print("[yellow]Adding them to the end of the file...[/yellow]")
            for key in missing_keys:
                new_lines.append(f"{key}={updates[key]}\n")
                console.print(f"[dim]  Adding {key}={updates[key]}[/dim]")

        # Write updated dietpi.txt
        temp_dietpi_txt = Path("/tmp/dietpi.txt")
        temp_dietpi_txt.write_text("".join(new_lines))
        subprocess.run(["sudo", "cp", str(temp_dietpi_txt), str(dietpi_txt_path)], check=True)
        temp_dietpi_txt.unlink()

        console.print("[green]✓ Updated dietpi.txt[/green]")

        # Verify the changes were written
        console.print("[dim]Verifying changes...[/dim]")
        with open(dietpi_txt_path) as f:
            verify_lines = f.readlines()
        for key, expected_value in updates.items():
            found = False
            for line in verify_lines:
                if line.strip().startswith(f"{key}="):
                    actual_value = line.strip().split("=", 1)[1]
                    if actual_value == expected_value:
                        console.print(f"[dim]  ✓ Verified {key}={expected_value}[/dim]")
                        found = True
                    else:
                        console.print(
                            f"[yellow]  ⚠ {key} has value '{actual_value}' "
                            f"instead of '{expected_value}'[/yellow]"
                        )
                        found = True
                    break
            if not found:
                console.print(f"[yellow]  ⚠ Could not verify {key} in written file[/yellow]")

        # Configure WiFi if enabled
        if config.get("enable_wifi"):
            dietpi_wifi_path = boot_mount / "dietpi-wifi.txt"
            if dietpi_wifi_path.exists():
                wifi_content = f"""# WiFi settings
aWIFI_SSID[0]='{config["wifi_ssid"]}'
aWIFI_KEY[0]='{config["wifi_password"]}'
"""
                temp_wifi = Path("/tmp/dietpi-wifi.txt")
                temp_wifi.write_text(wifi_content)
                subprocess.run(["sudo", "cp", str(temp_wifi), str(dietpi_wifi_path)], check=True)
                temp_wifi.unlink()
                console.print("[green]✓ Configured WiFi[/green]")

        # Enable SPI for ePaper HAT
        if config.get("enable_spi"):
            # Check if this is a Raspberry Pi (has config.txt)
            config_txt_path = boot_mount / "config.txt"
            dietpi_env_path = boot_mount / "dietpiEnv.txt"

            if config_txt_path.exists():
                # Raspberry Pi - use config.txt dtparam
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

                temp_config = Path("/tmp/dietpi_config_txt")
                temp_config.write_text(config_content)
                subprocess.run(
                    ["sudo", "cp", str(temp_config), str(config_txt_path)],
                    check=True,
                )
                temp_config.unlink()
                console.print("[green]✓ SPI enabled for ePaper HAT (Raspberry Pi)[/green]")

            elif dietpi_env_path.exists():
                # SBC with dietpiEnv.txt - use device tree overlay
                result = subprocess.run(
                    ["sudo", "cat", str(dietpi_env_path)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                env_content = result.stdout

                # Determine which SPI overlay to use based on device
                # Orange Pi Zero 2W: Allwinner H618 SPI1
                # Orange Pi 5 series: RK3588 SPI4-M0 is available on GPIO header
                # ROCK 5B: RK3588 SPI1-M1 or SPI3-M1 depending on configuration
                spi_overlay = None
                if device_key == "orange_pi_0w2":
                    spi_overlay = "spi-spidev"  # Allwinner H618
                elif device_key == "rock_5b":
                    spi_overlay = "rk3588-spi1-m1-cs0-spidev"  # RK3588
                elif device_key in ["orange_pi_5_plus", "orange_pi_5_pro"]:
                    spi_overlay = "rk3588-spi4-m0-cs1-spidev"  # RK3588

                if spi_overlay:
                    # Check if overlays line exists
                    overlays_added = False
                    new_lines = []
                    for line in env_content.split("\n"):
                        if line.startswith("overlays="):
                            # Add SPI overlay to existing overlays line
                            if spi_overlay not in line:
                                line = line.rstrip() + f" {spi_overlay}"
                            overlays_added = True
                        new_lines.append(line)

                    # If no overlays line exists, add it
                    if not overlays_added:
                        new_lines.append(f"overlays={spi_overlay}")

                    # Add spidev bus parameter if not present
                    if "param_spidev_spi_bus=" not in env_content:
                        new_lines.append("param_spidev_spi_bus=0")

                    env_content = "\n".join(new_lines)

                    temp_env = Path("/tmp/dietpi_env_txt")
                    temp_env.write_text(env_content)
                    subprocess.run(
                        ["sudo", "cp", str(temp_env), str(dietpi_env_path)],
                        check=True,
                    )
                    temp_env.unlink()

                    # Determine chip description for message
                    chip_desc = "Allwinner H618" if device_key == "orange_pi_0w2" else "RK3588"
                    msg = f"✓ SPI enabled for ePaper HAT ({chip_desc} overlay: {spi_overlay})"
                    console.print(f"[green]{msg}[/green]")
                else:
                    msg = "Note: SPI configuration for this device not yet implemented"
                    console.print(f"[yellow]{msg}[/yellow]")

            else:
                # Other SBC types not yet implemented
                console.print(
                    "[yellow]Note: SPI configuration for this device not yet implemented[/yellow]"
                )

        # Copy installer script if requested (handles preservation for DietPi automatically)
        modified_install_script = copy_installer_script(boot_mount, config, os_key, device_key)

        # Copy BirdNET-Pi pre-configuration file if any settings provided
        config_file = copy_birdnetpi_config(boot_mount, config, os_key, device_key)

        # CRITICAL: Also copy install.sh and config to rootfs partition
        # The DIETPISETUP partition (boot_mount) will be deleted after first boot
        # So we must also place install.sh and config on the persistent rootfs partition
        if config.get("copy_installer") and modified_install_script:
            console.print("[cyan]Copying install.sh to rootfs partition...[/cyan]")

            # Mount rootfs partition (usually partition 2 on DietPi)
            rootfs_mount = None
            rootfs_partition = None

            try:
                if platform.system() == "Darwin":
                    # On macOS, use anylinuxfs to mount the ext4 rootfs partition
                    # Check if anylinuxfs is installed
                    anylinuxfs_path = shutil.which("anylinuxfs")
                    mount_result = None
                    rootfs_partition_name = None
                    volumes_path = Path("/Volumes")
                    initial_volumes: set[Path] = set()

                    if not anylinuxfs_path:
                        console.print(
                            "[yellow]anylinuxfs not found - skipping rootfs mount[/yellow]"
                        )
                        console.print(
                            "[yellow]Automation scripts will preserve "
                            "install.sh during first boot[/yellow]"
                        )
                    else:
                        # Find the Linux Filesystem partition (rootfs)
                        # On Orange Pi 5 Pro: partition 1 is rootfs, partition 2 is DIETPISETUP
                        rootfs_partition_name = f"{device}s1"

                        console.print(
                            f"[cyan]Mounting {rootfs_partition_name} using anylinuxfs...[/cyan]"
                        )
                        console.print(
                            "[dim]This may take 10-15 seconds to start the microVM...[/dim]"
                        )

                        # Unmount any existing anylinuxfs mount first
                        subprocess.run(
                            ["sudo", "anylinuxfs", "unmount"],
                            capture_output=True,
                            check=False,
                            timeout=10,
                        )
                        time.sleep(2)

                        # Get list of volumes BEFORE anylinuxfs mount
                        initial_volumes = (
                            set(volumes_path.iterdir()) if volumes_path.exists() else set()
                        )

                        # Mount with anylinuxfs
                        mount_result = subprocess.run(
                            ["sudo", "anylinuxfs", rootfs_partition_name, "-w", "false"],
                            capture_output=False,  # Allow password prompt
                            check=False,
                        )

                    if anylinuxfs_path and mount_result and mount_result.returncode == 0:
                        # Wait for mount to appear in /Volumes
                        console.print("[dim]Waiting for mount to appear...[/dim]")

                        for attempt in range(60):
                            time.sleep(1)

                            # Find new volumes that appeared after anylinuxfs mount
                            current_volumes = (
                                set(volumes_path.iterdir()) if volumes_path.exists() else set()
                            )
                            new_volumes = current_volumes - initial_volumes

                            # Look for a new volume that looks like a Linux filesystem
                            for potential_mount in new_volumes:
                                if potential_mount.is_dir():
                                    # Check if it looks like a rootfs (has /etc, /root, /usr)
                                    if (
                                        (potential_mount / "etc").exists()
                                        and (potential_mount / "root").exists()
                                        and (potential_mount / "usr").exists()
                                    ):
                                        rootfs_mount = potential_mount
                                        rootfs_partition = rootfs_partition_name
                                        break

                            if rootfs_mount:
                                break

                            if attempt % 5 == 0 and attempt > 0:
                                console.print(f"[dim]Still waiting... ({attempt}s)[/dim]")

                        if rootfs_mount and rootfs_mount.exists():
                            console.print(f"[green]✓ Mounted at {rootfs_mount}[/green]")

                            # Ensure /root directory exists on rootfs
                            root_dir = rootfs_mount / "root"
                            subprocess.run(["sudo", "mkdir", "-p", str(root_dir)], check=True)

                            # Copy modified install.sh to /root on rootfs
                            # Use dd to avoid extended attributes issues with macOS
                            install_dest = root_dir / "install.sh"
                            subprocess.run(
                                [
                                    "sudo",
                                    "dd",
                                    f"if={modified_install_script}",
                                    f"of={install_dest}",
                                    "bs=1m",
                                ],
                                check=True,
                                capture_output=True,
                            )
                            subprocess.run(["sudo", "chmod", "+x", str(install_dest)], check=True)

                            console.print(
                                "[green]✓ install.sh copied to rootfs:/root/install.sh[/green]"
                            )

                            # Also copy config file if it was created
                            if config_file and config_file.exists():
                                config_dest = root_dir / "birdnetpi_config.json"
                                subprocess.run(
                                    [
                                        "sudo",
                                        "dd",
                                        f"if={config_file}",
                                        f"of={config_dest}",
                                        "bs=1m",
                                    ],
                                    check=True,
                                    capture_output=True,
                                )
                                console.print(
                                    "[green]✓ birdnetpi_config.json copied to "
                                    "rootfs:/root/birdnetpi_config.json[/green]"
                                )

                            console.print(
                                "[dim]Files persist after DIETPISETUP partition deletion[/dim]"
                            )
                        else:
                            console.print(
                                "[yellow]Could not find anylinuxfs mount after 60s[/yellow]"
                            )
                            console.print(
                                "[yellow]Automation scripts will preserve "
                                "install.sh during first boot[/yellow]"
                            )
                    elif anylinuxfs_path:
                        console.print(
                            "[yellow]anylinuxfs mount failed - using boot partition only[/yellow]"
                        )
                        console.print(
                            "[yellow]Automation scripts will preserve "
                            "install.sh during first boot[/yellow]"
                        )
                else:
                    # On Linux, mount partition 2 (rootfs)
                    rootfs_partition = f"{device}2"
                    rootfs_mount = Path("/mnt/dietpi_rootfs")
                    rootfs_mount.mkdir(parents=True, exist_ok=True)

                    subprocess.run(
                        ["sudo", "mount", rootfs_partition, str(rootfs_mount)], check=True
                    )

                    # Ensure /root directory exists on rootfs
                    root_dir = rootfs_mount / "root"
                    subprocess.run(["sudo", "mkdir", "-p", str(root_dir)], check=True)

                    # Copy modified install.sh to /root on rootfs
                    install_dest = root_dir / "install.sh"
                    subprocess.run(
                        ["sudo", "cp", str(modified_install_script), str(install_dest)], check=True
                    )
                    subprocess.run(["sudo", "chmod", "+x", str(install_dest)], check=True)

                    console.print("[green]✓ install.sh copied to rootfs:/root/install.sh[/green]")
                    console.print("[dim]Persists after DIETPISETUP partition deletion[/dim]")

            finally:
                # Unmount rootfs if we mounted it
                if rootfs_mount and rootfs_partition:
                    if platform.system() == "Darwin":
                        # Unmount anylinuxfs
                        console.print("[cyan]Unmounting anylinuxfs...[/cyan]")
                        try:
                            subprocess.run(
                                ["sudo", "anylinuxfs", "unmount"],
                                check=True,
                                timeout=10,
                                capture_output=True,
                            )
                            console.print("[green]✓ anylinuxfs unmounted[/green]")
                        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                            # Try force stop if unmount fails
                            subprocess.run(
                                ["sudo", "anylinuxfs", "stop"],
                                check=False,
                                timeout=5,
                                capture_output=True,
                            )
                    else:
                        subprocess.run(["sudo", "umount", str(rootfs_mount)], check=False)

    finally:
        # Clean up temporary config file if it exists
        if config_file and config_file.exists():
            config_file.unlink()

        # Unmount
        console.print("[cyan]Unmounting boot partition...[/cyan]")
        if platform.system() == "Darwin":
            subprocess.run(["diskutil", "unmount", "force", str(boot_mount)], check=True)
        else:
            subprocess.run(["sudo", "umount", str(boot_mount)], check=True)

    console.print("[green]✓ DietPi boot partition configured[/green]")


def configure_boot_partition_new(
    device: str,
    config: dict[str, Any],
    os_key: str,
    device_key: str,
) -> None:
    """Configure the bootfs partition with user settings."""
    image_info = OS_IMAGES[os_key]["devices"][device_key]
    is_dietpi = image_info.get("is_dietpi", False)

    # DietPi uses different configuration method
    if is_dietpi:
        configure_dietpi_boot(device, config, os_key, device_key)
        return

    # Raspbian/other OS
    requires_portability = image_info.get("requires_portability", False)

    # Create a legacy pi_version string for compatibility with existing code
    if requires_portability:
        pi_version = "Le Potato (Raspbian)"
    else:
        pi_version = image_info["name"]

    # Call the existing function with the legacy interface
    configure_boot_partition(device, config, pi_version, os_key, device_key)


def configure_boot_partition(  # noqa: C901
    device: str,
    config: dict[str, Any],
    pi_version: str,
    os_key: str,
    device_key: str,
) -> None:
    """Configure the bootfs partition with user settings (legacy interface)."""
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
        copy_installer_script(boot_mount, config, os_key, device_key)

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

        # Copy BirdNET-Pi pre-configuration file if any settings provided
        copy_birdnetpi_config(boot_mount, config)

    finally:
        # Unmount
        if platform.system() == "Darwin":
            subprocess.run(["diskutil", "unmount", "force", str(boot_mount)], check=True)
        else:
            subprocess.run(["sudo", "umount", str(boot_mount)], check=True)

    console.print("[green]✓ Boot partition configured[/green]")


def run_configuration_wizard() -> dict[str, Any] | None:
    """Run the Textual TUI wizard to gather configuration."""
    app = FlasherWizardApp(OS_PROPERTIES)
    return app.run()


def print_config_summary(config: dict[str, Any]) -> None:
    """Print configuration summary to terminal for reference."""
    console.print()
    console.print(Panel.fit("[bold green]Configuration Summary[/bold green]", border_style="green"))
    console.print()

    # Create summary table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Setting", style="cyan bold")
    table.add_column("Value", style="white")

    # OS and Device
    table.add_row("Operating System", config.get("os_key", "N/A"))
    table.add_row("Target Device", config.get("device_key", "N/A"))

    # Network
    if config.get("enable_wifi"):
        table.add_row("WiFi SSID", config.get("wifi_ssid", ""))
        table.add_row("WiFi Auth", config.get("wifi_auth", "WPA-PSK"))
    else:
        table.add_row("WiFi", "Disabled (Ethernet only)")

    # System
    table.add_row("Hostname", config.get("hostname", ""))
    table.add_row("Username", config.get("username", ""))

    # Advanced
    table.add_row("Preserve Installer", "Yes" if config.get("copy_installer") else "No")
    table.add_row("Enable SPI", "Yes" if config.get("enable_spi") else "No")
    table.add_row("GPIO Debug", "Yes" if config.get("gpio_debug") else "No")

    # BirdNET (optional)
    if config.get("device_name"):
        table.add_row("Device Name", config["device_name"])
    if config.get("latitude") is not None:
        table.add_row("Location", f"{config['latitude']}, {config['longitude']}")
    if config.get("timezone"):
        table.add_row("Timezone", config["timezone"])
    if config.get("language"):
        table.add_row("Language", config["language"])

    console.print(table)
    console.print()


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
def main(save_config_flag: bool, device_index: int | None, device_type: str | None) -> None:  # noqa: C901
    """Flash Raspberry Pi OS to SD card and configure for BirdNET-Pi."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]BirdNET-Pi SD Card Flasher[/bold cyan]\n"
            "[dim]Create bootable Raspberry Pi OS SD cards configured for BirdNET-Pi[/dim]",
            border_style="cyan",
        )
    )

    # Run TUI wizard to gather configuration
    config = run_configuration_wizard()

    # Handle cancellation
    if config is None:
        console.print("[yellow]Configuration cancelled[/yellow]")
        return

    # Print configuration summary to terminal scrollback
    print_config_summary(config)

    # Extract os_key and device_key from config
    os_key = config["os_key"]
    device_key = config["device_key"]

    # Select SD card device
    device = select_device(device_index=device_index)

    # Download image
    download_dir = Path.home() / ".cache" / "birdnetpi" / "images"
    download_dir.mkdir(parents=True, exist_ok=True)
    image_path = download_image_new(os_key, device_key, download_dir)

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
    image_info = OS_IMAGES[os_key]["devices"][device_key]
    is_armbian = image_info.get("is_armbian", False)
    is_dietpi = image_info.get("is_dietpi", False)

    if is_armbian:
        # Use anylinuxfs to configure Armbian ext4 partition
        configure_armbian_with_anylinuxfs(device, config, os_key, device_key)
    elif is_dietpi:
        # DietPi uses FAT32 boot partition like Raspbian
        configure_boot_partition_new(device, config, os_key, device_key)
    else:
        # Use standard FAT32 boot partition configuration
        configure_boot_partition_new(device, config, os_key, device_key)

    # Eject SD card
    console.print()
    console.print("[cyan]Ejecting SD card...[/cyan]")

    # Wait a bit for anylinuxfs unmount to fully complete
    time.sleep(2)

    if platform.system() == "Darwin":
        # Try to eject, but don't fail if it's still mounted
        result = subprocess.run(
            ["diskutil", "eject", device], check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            console.print("[yellow]Could not eject - disk may still be in use[/yellow]")
            console.print("[yellow]Please manually eject the SD card when ready[/yellow]")
            console.print(f"[dim]Error: {result.stderr.strip()}[/dim]")
    else:
        result = subprocess.run(
            ["sudo", "eject", device], check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            console.print("[yellow]Could not eject - disk may still be in use[/yellow]")
            console.print("[yellow]Please manually eject the SD card when ready[/yellow]")

    console.print()

    # Build summary message - look up display names from OS_IMAGES
    os_name = OS_IMAGES[os_key]["name"]
    device_name = OS_IMAGES[os_key]["devices"][device_key]["name"]
    requires_portability = image_info.get("requires_portability", False)

    summary_parts = [
        "[bold green]✓ SD Card Ready![/bold green]\n",
        f"OS: [yellow]{os_name}[/yellow]",
        f"Device: [yellow]{device_name}[/yellow]",
        f"Hostname: [cyan]{config.get('hostname', 'birdnetpi')}[/cyan]",
        f"Admin User: [cyan]{config['admin_user']}[/cyan]",
        "SSH: [green]Enabled[/green]",
    ]

    # Add WiFi status
    if config.get("enable_wifi"):
        summary_parts.append(f"WiFi: [green]Configured ({config['wifi_ssid']})[/green]")
    else:
        summary_parts.append("WiFi: [yellow]Not configured (Ethernet required)[/yellow]")

    # Special instructions for devices requiring portability script
    if requires_portability:
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
    # Direct boot instructions for Armbian/DietPi
    elif is_armbian or is_dietpi:
        os_label = "Armbian" if is_armbian else "DietPi"
        summary_parts.append(f"Native {os_label}: [green]Configured and ready[/green]\n")

        # DietPi has special installer preservation
        if is_dietpi:
            caps = get_combined_capabilities(os_key, device_key)
            install_path = caps.get("install_sh_path", "/root/install.sh")
            summary_parts.append(
                f"[dim]Insert the SD card and power on your device.\n"
                f"First boot will configure the system and preserve install.sh to:\n"
                f"  [cyan]{install_path}[/cyan]\n\n"
                f"After first boot, SSH in and run:\n"
                f"  [cyan]sudo bash {install_path}[/cyan]\n\n"
                f"[yellow]Troubleshooting (if install.sh is missing):[/yellow]\n"
                f"  • Check logs: [cyan]cat /var/log/birdnetpi_*.log[/cyan]\n"
                f"  • Read [cyan]BIRDNETPI_README.txt[/cyan] on boot partition\n"
                f"  • Manual installation instructions in README[/dim]"
            )
        # Check if anylinuxfs was used for Armbian
        elif shutil.which("anylinuxfs"):
            summary_parts.append(
                "[dim]Insert the SD card into your device and power it on.\n"
                "First boot will apply pre-configuration automatically.\n\n"
                f"SSH in as [cyan]{config['admin_user']}[/cyan] and run:\n"
                "  [cyan]bash /boot/install.sh[/cyan]\n\n"
                "[yellow]Note:[/yellow] If WiFi was configured, it may take 1-2 minutes "
                "to connect on first boot.[/dim]"
            )
        else:
            summary_parts.append(
                "[dim]Insert the SD card into your device and power it on.\n"
                "[yellow]anylinuxfs not installed - using interactive setup:[/yellow]\n"
                "  1. Create a root password\n"
                "  2. Create a user account\n"
                "  3. Configure locale/timezone\n\n"
                "After setup, run: [cyan]bash /boot/install.sh[/cyan][/dim]"
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
