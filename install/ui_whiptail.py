"""Pre-installation UI using whiptail for configuration collection."""

import platform
import subprocess
from dataclasses import dataclass


@dataclass
class InstallConfig:
    """Configuration collected from user during pre-install."""

    site_name: str = "BirdNET-Pi"
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = "UTC"
    configure_wifi: bool = False
    wifi_ssid: str = ""
    wifi_password: str = ""


class WhiptailUI:
    """Whiptail-based UI for pre-installation configuration."""

    def __init__(self):
        """Initialize whiptail UI."""
        self.width = 70
        self.height = 20

    def show_welcome(self) -> bool:
        """Show welcome screen with system information.

        Returns:
            bool: True if user wants to continue, False to exit
        """
        # Get system info
        hostname = platform.node()
        machine = platform.machine()
        system = platform.system()

        message = f"""Welcome to BirdNET-Pi Installer!

System Information:
  Hostname: {hostname}
  Architecture: {machine}
  OS: {system}

This installer will:
  1. Install system dependencies
  2. Configure BirdNET-Pi services
  3. Set up audio capture and analysis
  4. Enable web interface

Requirements:
  - Raspberry Pi 3B or newer
  - 8GB+ SD card (16GB+ recommended)
  - Internet connection
  - Sudo privileges

Press OK to continue or Cancel to exit."""

        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "BirdNET-Pi Installer",
                "--yesno",
                message,
                str(self.height + 5),
                str(self.width),
            ],
            check=False,
        )
        return result.returncode == 0

    def collect_basic_config(self) -> InstallConfig:
        """Collect basic configuration from user.

        Returns:
            InstallConfig: User configuration
        """
        config = InstallConfig()

        # Site name
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "Site Configuration",
                "--inputbox",
                "Enter a name for this BirdNET-Pi station:",
                "10",
                str(self.width),
                config.site_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            config.site_name = result.stderr.strip() or config.site_name

        # Location - Latitude
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "Location Configuration",
                "--inputbox",
                "Enter latitude (decimal degrees, e.g., 43.6532):",
                "10",
                str(self.width),
                str(config.latitude),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                config.latitude = float(result.stderr.strip())
            except ValueError:
                pass

        # Location - Longitude
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "Location Configuration",
                "--inputbox",
                "Enter longitude (decimal degrees, e.g., -79.3832):",
                "10",
                str(self.width),
                str(config.longitude),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                config.longitude = float(result.stderr.strip())
            except ValueError:
                pass

        # Timezone
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "Timezone Configuration",
                "--inputbox",
                "Enter timezone (e.g., America/Toronto, Europe/London):",
                "10",
                str(self.width),
                config.timezone,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            config.timezone = result.stderr.strip() or config.timezone

        return config

    def ask_wifi_config(self) -> bool:
        """Ask if user wants to configure WiFi.

        Returns:
            bool: True if user wants to configure WiFi
        """
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "WiFi Configuration",
                "--yesno",
                "Would you like to configure WiFi now?\n\n"
                "Note: WiFi can also be configured later through\n"
                "the web interface or raspi-config.",
                "12",
                str(self.width),
            ],
            check=False,
        )
        return result.returncode == 0

    def collect_wifi_config(self) -> tuple[str, str]:
        """Collect WiFi credentials.

        Returns:
            tuple[str, str]: (SSID, password)
        """
        # SSID
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "WiFi Configuration",
                "--inputbox",
                "Enter WiFi network name (SSID):",
                "10",
                str(self.width),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        ssid = result.stderr.strip() if result.returncode == 0 else ""

        # Password
        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "WiFi Configuration",
                "--passwordbox",
                "Enter WiFi password:",
                "10",
                str(self.width),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        password = result.stderr.strip() if result.returncode == 0 else ""

        return ssid, password

    def show_config_summary(self, config: InstallConfig) -> bool:
        """Show configuration summary and ask for confirmation.

        Args:
            config: Installation configuration

        Returns:
            bool: True if user confirms, False to go back
        """
        wifi_status = f"SSID: {config.wifi_ssid}" if config.configure_wifi else "Not configured"

        message = f"""Configuration Summary:

Site Name: {config.site_name}
Location: {config.latitude}, {config.longitude}
Timezone: {config.timezone}
WiFi: {wifi_status}

Installation will:
  • Install system packages (~500MB)
  • Download BirdNET models (~150MB)
  • Set up systemd services
  • Configure web interface on port 8888

This will take approximately 10-15 minutes.

Proceed with installation?"""

        result = subprocess.run(
            [
                "whiptail",
                "--title",
                "Confirm Installation",
                "--yesno",
                message,
                str(self.height + 2),
                str(self.width),
            ],
            check=False,
        )
        return result.returncode == 0

    def show_error(self, message: str) -> None:
        """Show error message.

        Args:
            message: Error message to display
        """
        subprocess.run(
            [
                "whiptail",
                "--title",
                "Error",
                "--msgbox",
                message,
                "10",
                str(self.width),
            ],
            check=False,
        )

    def run_pre_install(self) -> InstallConfig | None:
        """Run complete pre-installation UI flow.

        Returns:
            InstallConfig: User configuration, or None if cancelled
        """
        # Welcome screen
        if not self.show_welcome():
            return None

        # Collect basic configuration
        config = self.collect_basic_config()

        # Ask about WiFi
        if self.ask_wifi_config():
            config.configure_wifi = True
            config.wifi_ssid, config.wifi_password = self.collect_wifi_config()

        # Show summary and confirm
        if not self.show_config_summary(config):
            return None

        return config
