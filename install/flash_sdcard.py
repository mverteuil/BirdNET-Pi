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
        "url": "https://downloads.raspberrypi.org/raspios_lite_armhf/images/raspios_lite_armhf-2024-07-04/2024-07-04-raspios-bookworm-armhf-lite.img.xz",
        "sha256": "TODO",  # TODO: Add real SHA256 hash from raspberrypi.org
    },
    "Pi Zero 2 W": {
        "url": "https://downloads.raspberrypi.org/raspios_lite_armhf/images/raspios_lite_armhf-2024-07-04/2024-07-04-raspios-bookworm-armhf-lite.img.xz",
        "sha256": "TODO",  # TODO: Add real SHA256 hash from raspberrypi.org
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


def list_block_devices() -> list[dict[str, str]]:
    """List available block devices (SD cards) on the system."""
    if platform.system() == "Darwin":
        # macOS
        result = subprocess.run(["diskutil", "list"], capture_output=True, text=True, check=True)
        devices = []
        current_device = None

        for line in result.stdout.splitlines():
            # Match device identifier like /dev/disk2
            if match := re.match(r"^(/dev/disk\d+)", line):
                current_device = match.group(1)
            # Look for size info in the device header
            elif current_device and "external, physical" in line.lower():
                # Get size from the line
                size_match = re.search(r"\*(\d+\.\d+\s+[A-Z]+)\*", line)
                size = size_match.group(1) if size_match else "Unknown"
                devices.append({"device": current_device, "size": size, "type": "SD Card"})
                current_device = None

        return devices
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

    models = list(PI_IMAGES.keys())
    for idx, model in enumerate(models, 1):
        table.add_row(str(idx), model)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[bold]Select Raspberry Pi model[/bold]",
        choices=[str(i) for i in range(1, len(models) + 1)],
    )

    return models[int(choice) - 1]


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


def get_config_from_prompts(saved_config: dict[str, Any] | None) -> dict[str, Any]:
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

    # Advanced settings
    if saved_config and "gpio_debug" in saved_config:
        config["gpio_debug"] = saved_config["gpio_debug"]
        console.print(f"[dim]Using saved GPIO debug: {config['gpio_debug']}[/dim]")
    else:
        config["gpio_debug"] = Confirm.ask("Enable GPIO Debugging (Advanced)?", default=False)

    if saved_config and "run_installer" in saved_config:
        config["run_installer"] = saved_config["run_installer"]
        console.print(f"[dim]Using saved run installer: {config['run_installer']}[/dim]")
    else:
        config["run_installer"] = Confirm.ask("Run installer on first boot?", default=True)

    return config


def flash_image(image_path: Path, device: str) -> None:
    """Flash the image to the SD card."""
    console.print()
    console.print(f"[cyan]Flashing {image_path.name} to {device}...[/cyan]")

    # Unmount device first
    if platform.system() == "Darwin":
        subprocess.run(["diskutil", "unmountDisk", device], check=True, stdout=subprocess.DEVNULL)

    # Decompress and flash
    if image_path.suffix == ".xz":
        console.print(
            "[yellow]Decompressing and flashing (this may take several minutes)...[/yellow]"
        )
        # Use shell pipeline: unxz -c image.xz | dd of=device
        with subprocess.Popen(["unxz", "-c", str(image_path)], stdout=subprocess.PIPE) as unxz:
            subprocess.run(
                ["sudo", "dd", f"of={device}", "bs=4M", "status=progress"],
                stdin=unxz.stdout,
                check=True,
            )
    else:
        subprocess.run(
            ["sudo", "dd", f"if={image_path}", f"of={device}", "bs=4M", "status=progress"],
            check=True,
        )

    subprocess.run(["sync"], check=True)
    console.print("[green]✓ Image flashed successfully[/green]")


def configure_boot_partition(device: str, config: dict[str, Any]) -> None:
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
        # Enable SSH
        (boot_mount / "ssh").touch()
        console.print("[green]✓ SSH enabled[/green]")

        # Configure user (userconf.txt format: username:encrypted_password)
        # Generate encrypted password
        password_hash = subprocess.run(
            ["openssl", "passwd", "-6", config["admin_password"]],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        userconf = boot_mount / "userconf.txt"
        userconf.write_text(f"{config['admin_user']}:{password_hash}\n")
        console.print(f"[green]✓ User configured: {config['admin_user']}[/green]")

        # Configure WiFi if enabled
        if config.get("enable_wifi"):
            wpa_conf = boot_mount / "wpa_supplicant.conf"
            wpa_conf.write_text(
                f"""country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={{
    ssid="{config["wifi_ssid"]}"
    psk="{config["wifi_password"]}"
    key_mgmt={config.get("wifi_auth", "WPA-PSK")}
}}
"""
            )
            console.print("[green]✓ WiFi configured[/green]")

        # GPIO debugging
        if config.get("gpio_debug"):
            config_txt = boot_mount / "config.txt"
            with open(config_txt, "a") as f:
                f.write("\n# GPIO Debugging\nenable_uart=1\n")
            console.print("[green]✓ GPIO debugging enabled[/green]")

        # Copy installer script if requested
        if config.get("run_installer"):
            install_script = Path(__file__).parent / "setup_app.py"
            if install_script.exists():
                shutil.copy(install_script, boot_mount / "birdnetpi_install.py")
                console.print("[green]✓ Installer copied to boot partition[/green]")
            else:
                console.print(
                    "[yellow]Warning: setup_app.py not found, skipping auto-installer[/yellow]"
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
    console.print(
        Panel.fit(
            "[bold green]✓ SD Card Ready![/bold green]\n\n"
            f"Raspberry Pi Model: [yellow]{pi_version}[/yellow]\n"
            f"Admin User: [cyan]{config['admin_user']}[/cyan]\n"
            f"WiFi Enabled: [cyan]{'Yes' if config.get('enable_wifi') else 'No'}[/cyan]\n"
            f"Auto-Installer: [cyan]{'Yes' if config.get('run_installer') else 'No'}[/cyan]\n\n"
            "[dim]You can now insert the SD card into your Raspberry Pi and power it on.[/dim]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
