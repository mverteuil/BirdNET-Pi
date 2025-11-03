"""System setup CLI for initial BirdNET-Pi configuration.

This tool runs during installation to configure critical system settings
before services start. It handles:
- Config file initialization
- Audio device auto-detection
- GPS auto-detection
- Interactive prompts for attended installs
- Boot volume pre-configuration support
"""

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import pytz
import sounddevice as sd
from gpsdclient.client import GPSDClient
from tzlocal import get_localzone

from birdnetpi.config.manager import ConfigManager
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.system.path_resolver import PathResolver


def detect_audio_devices() -> tuple[int | None, str]:
    """Detect and select the best audio input device.

    Priority:
    1. USB sound devices (always preferred)
    2. Best native sample rate among USB devices
    3. Fallback to best available device

    Returns:
        Tuple of (device_index, device_name)
    """
    devices: Any = sd.query_devices()

    usb_devices = []
    other_devices = []

    for idx, device in enumerate(devices):
        # Skip output-only devices
        if device["max_input_channels"] == 0:  # type: ignore[index]
            continue

        device_info = {
            "index": idx,
            "name": device["name"],  # type: ignore[index]
            "sample_rate": device["default_samplerate"],  # type: ignore[index]
            "channels": device["max_input_channels"],  # type: ignore[index]
        }

        # Check if USB device (common USB audio device name patterns)
        name_lower = device["name"].lower()  # type: ignore[index]
        usb_markers = ["usb", "webcam", "logitech", "blue"]
        if any(usb_marker in name_lower for usb_marker in usb_markers):
            usb_devices.append(device_info)
        else:
            other_devices.append(device_info)

    # Prefer USB devices, sorted by sample rate (higher is better)
    if usb_devices:
        best = max(usb_devices, key=lambda d: d["sample_rate"])
        return best["index"], best["name"]

    # Fallback to best non-USB device
    if other_devices:
        best = max(other_devices, key=lambda d: d["sample_rate"])
        return best["index"], best["name"]

    return None, "No input devices found"


def detect_gps() -> tuple[float | None, float | None, str | None]:
    """Detect GPS device and get location.

    Attempts to connect to gpsd and get a GPS fix. Waits up to 10 seconds
    for a valid position fix.

    Returns:
        Tuple of (latitude, longitude, timezone) or (None, None, None)
    """
    try:
        client = GPSDClient()
        # Try to get a GPS fix with timeout
        for packet in client.dict_stream(filter={"TPV"}):
            # TPV (Time-Position-Velocity) packets contain position data
            mode = packet.get("mode", 0)

            # mode 2 = 2D fix, mode 3 = 3D fix
            if mode >= 2:
                lat = packet.get("lat")
                lon = packet.get("lon")
                if lat is not None and lon is not None:
                    # Try to determine timezone from system
                    try:
                        tz = str(get_localzone())
                    except Exception:
                        tz = "UTC"
                    return float(lat), float(lon), tz

            # Only check a few packets before giving up
            break

    except Exception:
        # GPS not available (gpsd not running, no GPS device, etc.)
        pass

    return None, None, None


def get_boot_config() -> dict[str, str]:
    """Load pre-configuration from boot volume or root.

    Checks multiple locations for birdnetpi_config.txt:
    - /root/birdnetpi_config.txt (for DietPi, persists after DIETPISETUP deletion)
    - /boot/firmware/birdnetpi_config.txt (for Raspberry Pi OS)
    - /boot/birdnetpi_config.txt (fallback)

    Returns:
        Dict of pre-configured values (empty if not found)
    """
    # Check multiple locations (prioritize /root for DietPi)
    config_locations = [
        Path("/root/birdnetpi_config.txt"),
        Path("/boot/firmware/birdnetpi_config.txt"),
        Path("/boot/birdnetpi_config.txt"),
    ]

    boot_config_path = None
    for path in config_locations:
        if path.exists():
            boot_config_path = path
            break

    if not boot_config_path:
        return {}

    config = {}
    try:
        for line in boot_config_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    except Exception as e:
        click.echo(f"Warning: Could not read boot config: {e}", err=True)

    return config


def is_attended_install() -> bool:
    """Check if this is an attended installation.

    Returns:
        True if stdin is a TTY (interactive), False otherwise
    """
    return sys.stdin.isatty()


def get_supported_os_options() -> dict[str, str]:
    """Get supported operating systems.

    Returns:
        Dict mapping OS keys to display names
    """
    return {
        "raspbian": "Raspberry Pi OS",
        "armbian": "Armbian",
        "dietpi": "DietPi",
    }


def get_supported_devices() -> dict[str, str]:
    """Get supported device types.

    Returns:
        Dict mapping device keys to display names
    """
    return {
        "pi_zero_2w": "Raspberry Pi Zero 2W",
        "pi_3b": "Raspberry Pi 3B/3B+",
        "pi_4b": "Raspberry Pi 4B",
        "pi_5": "Raspberry Pi 5",
        "orange_pi_0w2": "Orange Pi Zero 2W",
        "orange_pi_5_plus": "Orange Pi 5 Plus",
        "orange_pi_5_pro": "Orange Pi 5 Pro",
        "rock_5b": "Radxa ROCK 5B",
        "other": "Other (generic configuration)",
    }


def prompt_os_selection(default: str = "raspbian") -> str:
    """Prompt user to select an operating system.

    Args:
        default: Default OS key

    Returns:
        Selected OS key
    """
    os_options = get_supported_os_options()

    click.echo("\nSupported Operating Systems:")
    click.echo("-" * 60)
    for key, name in os_options.items():
        marker = "(default)" if key == default else ""
        click.echo(f"  {key:12} - {name} {marker}")

    while True:
        os_key = click.prompt("\nOperating System", default=default, show_default=True)
        if os_key in os_options:
            return os_key
        else:
            click.echo(f"  ✗ Invalid OS: {os_key}")
            click.echo(f"  Please enter one of: {', '.join(os_options.keys())}")


def prompt_device_selection(default: str = "pi_4b") -> str:
    """Prompt user to select a device type.

    Args:
        default: Default device key

    Returns:
        Selected device key
    """
    devices = get_supported_devices()

    click.echo("\nSupported Devices:")
    click.echo("-" * 60)
    for key, name in devices.items():
        marker = "(default)" if key == default else ""
        click.echo(f"  {key:18} - {name} {marker}")

    while True:
        device_key = click.prompt("\nDevice Type", default=default, show_default=True)
        if device_key in devices:
            return device_key
        else:
            click.echo(f"  ✗ Invalid device: {device_key}")
            click.echo(f"  Please enter one of: {', '.join(devices.keys())}")


def get_common_timezones() -> list[str]:
    """Get list of common timezones for user selection.

    Returns:
        List of timezone names (e.g., "America/New_York")
    """
    return pytz.common_timezones


def prompt_timezone_selection(default: str = "UTC") -> str:
    """Prompt user to select a timezone.

    Args:
        default: Default timezone to use

    Returns:
        Selected timezone name
    """
    timezones = get_common_timezones()

    click.echo("\nCommon timezones:")
    click.echo("  Americas: America/New_York, America/Chicago, America/Los_Angeles")
    click.echo("  Europe: Europe/London, Europe/Paris, Europe/Berlin")
    click.echo("  Asia: Asia/Tokyo, Asia/Shanghai, Asia/Kolkata")
    click.echo("  Pacific: Pacific/Auckland, Australia/Sydney")
    click.echo("\nFor full list, see: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")

    while True:
        tz = click.prompt("\nTimezone", default=default, show_default=True)
        if tz in timezones:
            return tz
        else:
            click.echo(f"  ✗ Invalid timezone: {tz}")
            click.echo("  Please enter a valid timezone (e.g., America/New_York)")


def get_supported_languages(path_resolver: PathResolver) -> dict[str, tuple[str, int]]:
    """Get supported language codes from species databases.

    Queries the IOC reference database to get all languages with their
    translation counts. Falls back to a hardcoded list if database not available.

    Args:
        path_resolver: PathResolver to locate database

    Returns:
        Dict mapping language codes to (language_name, translation_count) tuples
    """
    ioc_db_path = path_resolver.get_ioc_database_path()

    # Fallback languages if database not available
    fallback = {
        "en": ("English", 10983),
        "es": ("Spanish / Español", 10823),
        "fr": ("French / Français", 10983),
        "de": ("German / Deutsch", 10785),
        "it": ("Italian / Italiano", 10006),
        "pt": ("Portuguese / Português", 10981),
        "nl": ("Dutch / Nederlands", 10983),
        "ru": ("Russian / Русский", 10567),
        "zh": ("Chinese / 中文", 10983),
        "ja": ("Japanese / 日本語", 10537),
    }

    if not ioc_db_path.exists():
        return fallback

    try:
        conn = sqlite3.connect(ioc_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT language_code, language_name, translation_count "
            "FROM languages "
            "ORDER BY translation_count DESC"
        )
        results = cursor.fetchall()
        conn.close()

        languages = {code: (name, count) for code, name, count in results if count > 0}
        # Always include English (scientific names) even though it's not in the database
        languages["en"] = ("English", 10983)
        return languages
    except Exception:
        return fallback


def prompt_language_selection(path_resolver: PathResolver, default: str = "en") -> str:
    """Prompt user to select a language.

    Args:
        path_resolver: PathResolver to locate database
        default: Default language code

    Returns:
        Selected language code
    """
    languages = get_supported_languages(path_resolver)

    click.echo("\nSupported languages (sorted by species coverage):")
    click.echo("-" * 60)

    # Show top languages with full coverage (>10,000 species)
    full_coverage = {k: v for k, v in languages.items() if v[1] >= 10000}
    if full_coverage:
        click.echo("\nFull coverage (>10,000 species):")
        for code, (name, count) in sorted(
            full_coverage.items(), key=lambda x: x[1][1], reverse=True
        )[:10]:
            click.echo(f"  {code:6} - {name:30} ({count:,} species)")

    # Show partial coverage languages
    partial_coverage = {k: v for k, v in languages.items() if 1000 < v[1] < 10000}
    if partial_coverage:
        click.echo("\nPartial coverage (1,000-10,000 species):")
        for code, (name, count) in sorted(
            partial_coverage.items(), key=lambda x: x[1][1], reverse=True
        )[:10]:
            click.echo(f"  {code:6} - {name:30} ({count:,} species)")

    click.echo(f"\nTotal languages available: {len(languages)}")

    while True:
        lang = click.prompt("\nLanguage code", default=default, show_default=True)
        if lang in languages:
            return lang
        else:
            click.echo(f"  ✗ Invalid language code: {lang}")
            click.echo("  Please enter a valid language code (e.g., en, es, fr)")


def configure_audio_device(config: BirdNETConfig) -> None:
    """Auto-detect and configure audio device.

    Args:
        config: BirdNETConfig to update
    """
    click.echo()
    click.echo("Detecting audio devices...")
    device_index, device_name = detect_audio_devices()
    if device_index is not None:
        click.echo(f"  ✓ Selected: {device_name} (index {device_index})")
        config.audio_device_index = device_index
    else:
        click.echo(f"  ✗ {device_name}")


def configure_gps(config: BirdNETConfig) -> tuple[float | None, float | None]:
    """Auto-detect and configure GPS.

    Args:
        config: BirdNETConfig to update

    Returns:
        Tuple of (latitude, longitude) from detection
    """
    click.echo()
    click.echo("Checking for GPS...")
    lat, lon, tz = detect_gps()
    if lat is not None and lon is not None:
        click.echo(f"  ✓ GPS found: {lat}, {lon}")
        config.latitude = lat
        config.longitude = lon
        if tz:
            config.timezone = tz
    else:
        click.echo("  ○ No GPS detected")
    return lat, lon


def configure_device_name(
    config: BirdNETConfig,
    boot_config: dict[str, str],
) -> None:
    """Configure device name via prompt or boot config.

    Args:
        config: BirdNETConfig to update
        boot_config: Boot volume pre-configuration
    """
    if "device_name" not in boot_config:
        default_name = config.site_name or "BirdNET-Pi"
        device_name_input = click.prompt("Device name", default=default_name, show_default=True)
        config.site_name = device_name_input
    else:
        config.site_name = boot_config["device_name"]
        click.echo(f"Device name: {config.site_name} (from boot config)")


def configure_location(
    config: BirdNETConfig,
    boot_config: dict[str, str],
    lat_detected: float | None,
) -> None:
    """Configure location via prompt or boot config.

    Args:
        config: BirdNETConfig to update
        boot_config: Boot volume pre-configuration
        lat_detected: Latitude from GPS detection (None if not detected)
    """
    if lat_detected is None and "latitude" not in boot_config:
        if click.confirm("Configure location now?", default=True):
            lat_input = click.prompt("Latitude", type=float)
            lon_input = click.prompt("Longitude", type=float)
            config.latitude = lat_input
            config.longitude = lon_input

            # Prompt for timezone with validation
            tz_input = prompt_timezone_selection(default="UTC")
            config.timezone = tz_input
        else:
            click.echo("  Skipping location (can configure later in web UI)")
    elif "latitude" in boot_config and "longitude" in boot_config:
        config.latitude = float(boot_config["latitude"])
        config.longitude = float(boot_config["longitude"])
        if "timezone" in boot_config:
            config.timezone = boot_config["timezone"]
        loc_msg = f"Location: {config.latitude}, {config.longitude} (from boot config)"
        click.echo(loc_msg)


def configure_os(
    boot_config: dict[str, str],
) -> str:
    """Configure operating system via prompt or boot config.

    Args:
        boot_config: Boot volume pre-configuration

    Returns:
        Selected OS key
    """
    # Check both os_key (new) and os (legacy) for backwards compatibility
    os_key = boot_config.get("os_key") or boot_config.get("os")
    if not os_key:
        os_key = prompt_os_selection(default="raspbian")
        click.echo(f"  Selected OS: {get_supported_os_options()[os_key]}")
        return os_key
    else:
        click.echo(f"OS: {get_supported_os_options().get(os_key, os_key)} (from boot config)")
        return os_key


def configure_device(
    boot_config: dict[str, str],
) -> str:
    """Configure device type via prompt or boot config.

    Args:
        boot_config: Boot volume pre-configuration

    Returns:
        Selected device key
    """
    # Check both device_key (new) and device (legacy) for backwards compatibility
    device_key = boot_config.get("device_key") or boot_config.get("device")
    if not device_key:
        device_key = prompt_device_selection(default="pi_4b")
        click.echo(f"  Selected device: {get_supported_devices()[device_key]}")
        return device_key
    else:
        device_name = get_supported_devices().get(device_key, device_key)
        click.echo(f"Device: {device_name} (from boot config)")
        return device_key


def configure_language(
    config: BirdNETConfig,
    boot_config: dict[str, str],
    path_resolver: PathResolver,
) -> None:
    """Configure language via prompt or boot config.

    Args:
        config: BirdNETConfig to update
        boot_config: Boot volume pre-configuration
        path_resolver: PathResolver to locate databases
    """
    if "language" not in boot_config:
        # Use dynamic language selection from database
        language_input = prompt_language_selection(path_resolver, default="en")
        config.language = language_input
    else:
        config.language = boot_config["language"]
        click.echo(f"Language: {config.language} (from boot config)")


def initialize_config(
    path_resolver: PathResolver,
) -> tuple[Path, BirdNETConfig, dict[str, str]]:
    """Initialize configuration from template.

    Args:
        path_resolver: PathResolver instance

    Returns:
        Tuple of (config_path, config, boot_config)
    """
    config_manager = ConfigManager(path_resolver)
    config_path = path_resolver.get_birdnetpi_config_path()

    # Load boot volume pre-configuration
    boot_config = get_boot_config()
    if boot_config:
        click.echo("Found pre-configuration from boot volume")

    # Initialize config from template
    click.echo("Initializing configuration...")
    template_path = path_resolver.app_dir / "config_templates" / "birdnetpi.yaml"
    if not template_path.exists():
        click.echo(f"Error: Template not found at {template_path}", err=True)
        sys.exit(1)

    # Copy template to config location
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(template_path.read_text())

    # Load config
    config = config_manager.load()

    return config_path, config, boot_config


def set_system_timezone(config: BirdNETConfig) -> None:
    """Set the system timezone based on the configuration.

    Uses timedatectl to set the system timezone to match the configured timezone.
    This ensures that system logs and timestamps match the user's expected timezone.

    Args:
        config: Configuration containing the timezone setting
    """
    timezone = config.timezone
    if not timezone or timezone == "UTC":
        click.echo("  Timezone is UTC (default), skipping system timezone update")
        return

    try:
        # Validate timezone exists in pytz
        if timezone not in pytz.all_timezones:
            click.echo(f"  ! Invalid timezone '{timezone}', skipping system timezone update")
            return

        # Try timedatectl first (requires systemd/DBus)
        result = subprocess.run(
            ["timedatectl", "set-timezone", timezone],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            click.echo(f"  ✓ System timezone set to {timezone}")
        elif "Failed to connect to bus" in result.stderr:
            # Fallback for systems without DBus (e.g., DietPi during installation)
            # Directly set timezone files
            try:
                # Write timezone to /etc/timezone
                with Path("/etc/timezone").open("w") as f:
                    f.write(f"{timezone}\n")

                # Link /etc/localtime to the zoneinfo file
                zoneinfo_path = Path(f"/usr/share/zoneinfo/{timezone}")
                localtime_path = Path("/etc/localtime")

                if zoneinfo_path.exists():
                    # Remove old symlink/file
                    localtime_path.unlink(missing_ok=True)
                    # Create new symlink
                    localtime_path.symlink_to(zoneinfo_path)
                    click.echo(f"  ✓ System timezone set to {timezone} (fallback method)")
                else:
                    click.echo(f"  ! Timezone file not found: {zoneinfo_path}")
            except Exception as fallback_error:
                click.echo(f"  ! Failed to set timezone (fallback): {fallback_error}")
        else:
            click.echo(f"  ! Failed to set system timezone: {result.stderr.strip()}")
    except Exception as e:
        click.echo(f"  ! Error setting system timezone: {e}")


@click.command()
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Run in non-interactive mode (use defaults/auto-detection only)",
)
def main(non_interactive: bool) -> None:
    """Configure BirdNET-Pi system settings.

    This tool initializes the configuration file and sets up critical
    system settings before services start.
    """
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)

    click.echo("=" * 60)
    click.echo("BirdNET-Pi System Setup")
    click.echo("=" * 60)
    click.echo()

    # Check if config already exists
    config_path = path_resolver.get_birdnetpi_config_path()
    if config_path.exists():
        click.echo(f"Configuration already exists at {config_path}")
        click.echo("Skipping setup.")
        return

    # Initialize config from template
    config_path, config, boot_config = initialize_config(path_resolver)

    # Auto-detect audio device
    configure_audio_device(config)

    # Auto-detect GPS
    lat_detected, _ = configure_gps(config)

    # Interactive prompts (only if attended AND values not pre-configured)
    attended = is_attended_install() and not non_interactive

    if attended:
        click.echo()
        click.echo("Configuration Prompts")
        click.echo("-" * 60)

        # OS and device selection first
        os_key = configure_os(boot_config)
        device_key = configure_device(boot_config)

        # Store OS and device info in config for reference
        # Note: These aren't part of BirdNETConfig model, but we store them
        # for future use (e.g., OS-specific optimizations, device-specific settings)
        os_name = get_supported_os_options()[os_key]
        device_name = get_supported_devices()[device_key]
        click.echo(f"\nConfiguring for {os_name} on {device_name}")

        configure_device_name(config, boot_config)
        configure_location(config, boot_config, lat_detected)
        configure_language(config, boot_config, path_resolver)

    # Save config
    click.echo()
    click.echo("Saving configuration...")
    config_manager.save(config)
    click.echo(f"  ✓ Configuration saved to {config_path}")

    # Set system timezone to match config
    click.echo()
    click.echo("Setting system timezone...")
    set_system_timezone(config)

    click.echo()
    click.echo("=" * 60)
    click.echo("System setup complete!")
    click.echo("=" * 60)


if __name__ == "__main__":
    main()
