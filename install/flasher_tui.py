"""Textual TUI for BirdNET-Pi SD Card Flasher Configuration.

This module provides a guided wizard interface for configuring SD card
flashing options using the Textual framework.
"""

import json
from pathlib import Path
from typing import Any

from textual import on  # type: ignore[import-untyped]
from textual.app import App, ComposeResult  # type: ignore[import-untyped]
from textual.containers import Container, Horizontal, Vertical  # type: ignore[import-untyped]
from textual.screen import ModalScreen  # type: ignore[import-untyped]
from textual.validation import Function, ValidationResult, Validator  # type: ignore[import-untyped]
from textual.widgets import (  # type: ignore[import-untyped]
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

# ============================================================================
# Capability Calculation
# ============================================================================


def get_combined_capabilities(
    os_key: str, device_key: str, os_properties: dict[str, Any], device_properties: dict[str, Any]
) -> dict[str, Any]:
    """Calculate combined capabilities from OS and device properties.

    Args:
        os_key: OS type (e.g., "raspbian", "armbian", "dietpi")
        device_key: Device key (e.g., "pi_4", "orangepi5")
        os_properties: OS properties dictionary
        device_properties: Device properties dictionary

    Returns:
        Dictionary of combined capabilities
    """
    os_props = os_properties.get(os_key, {})
    device_props = device_properties.get(device_key, {})

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


# ============================================================================
# Profile Management
# ============================================================================


class ProfileManager:
    """Manage saving/loading configuration profiles."""

    PROFILES_DIR = Path.home() / ".config" / "birdnetpi" / "profiles"

    @classmethod
    def save_profile(cls, name: str, config: dict[str, Any]) -> None:
        """Save configuration as named profile."""
        cls.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profile_path = cls.PROFILES_DIR / f"{name}.json"
        with open(profile_path, "w") as f:
            json.dump(config, f, indent=2)

    @classmethod
    def load_profile(cls, name: str) -> dict[str, Any] | None:
        """Load named profile."""
        profile_path = cls.PROFILES_DIR / f"{name}.json"
        if profile_path.exists():
            try:
                with open(profile_path) as f:
                    return json.load(f)
            except Exception as e:
                # Log error but return None
                print(f"Error loading profile {name}: {e}")
                return None
        return None

    @classmethod
    def list_profiles(cls) -> list[str]:
        """List available profile names."""
        if not cls.PROFILES_DIR.exists():
            return []
        return sorted([p.stem for p in cls.PROFILES_DIR.glob("*.json")])


# ============================================================================
# Validators
# ============================================================================


class HostnameValidator(Validator):
    """Validator for hostname fields."""

    def validate(self, value: str) -> ValidationResult:
        """Validate hostname is alphanumeric and >= 3 chars."""
        if not value:
            return self.failure("Hostname required")
        if not value.replace("-", "").isalnum():
            return self.failure("Only alphanumeric and hyphens allowed")
        if len(value) < 3:
            return self.failure("At least 3 characters required")
        return self.success()


class PasswordValidator(Validator):
    """Validator for password fields."""

    def validate(self, value: str) -> ValidationResult:
        """Validate password is at least 4 characters."""
        if not value:
            return self.failure("Password required")
        if len(value) < 4:
            return self.failure("At least 4 characters required")
        return self.success()


class LatitudeValidator(Validator):
    """Validator for latitude values."""

    def validate(self, value: str) -> ValidationResult:
        """Validate latitude is between -90 and 90."""
        if not value:
            return self.success()  # Optional field
        try:
            lat = float(value)
            if not -90 <= lat <= 90:
                return self.failure("Must be between -90 and 90")
            return self.success()
        except ValueError:
            return self.failure("Must be a valid number")


class LongitudeValidator(Validator):
    """Validator for longitude values."""

    def validate(self, value: str) -> ValidationResult:
        """Validate longitude is between -180 and 180."""
        if not value:
            return self.success()  # Optional field
        try:
            lon = float(value)
            if not -180 <= lon <= 180:
                return self.failure("Must be between -180 and 180")
            return self.success()
        except ValueError:
            return self.failure("Must be a valid number")


# ============================================================================
# TUI Screens
# ============================================================================


class FlasherWizardApp(App[dict | None]):
    """BirdNET-Pi SD Card Flasher Configuration Wizard.

    This TUI guides users through configuring all settings for flashing
    an SD card. Upon completion, it returns a configuration dictionary
    to the calling script for processing.
    """

    CSS_PATH = "flasher.tcss"

    def __init__(
        self,
        os_images: dict[str, Any],
        device_properties: dict[str, Any],
        os_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initialize wizard with OS and device data."""
        super().__init__()
        self.config: dict[str, Any] = {}
        self.os_images = os_images
        self.device_properties = device_properties
        self.os_properties = os_properties or {}
        self.is_loaded_profile = False  # Track if config is from loaded profile
        self.loaded_profile_name: str | None = None  # Track original profile name when editing

    def on_mount(self) -> None:
        """Start wizard with profile selection."""
        self.push_screen(ProfileLoadScreen(), self.handle_profile_load)

    def handle_profile_load(self, profile_config: dict[str, Any] | None) -> None:
        """Handle profile selection result."""
        if profile_config is None:
            # Start new configuration
            self.is_loaded_profile = False
            self.loaded_profile_name = None
            self.push_screen(OSSelectionScreen(self.os_images), self.handle_os_selection)
        elif profile_config == "CANCELLED":
            # User cancelled
            self.exit(None)
        else:
            # Loaded profile - extract and store profile name
            self.loaded_profile_name = profile_config.pop("__profile_name__", None)

            # Normalize old keys for compatibility
            if "os_key" in profile_config:
                # Normalize old capitalized OS keys (e.g., "DietPi" -> "dietpi")
                profile_config["os_key"] = profile_config["os_key"].lower()
            elif "os_type" in profile_config:
                # Old profiles used "os_type" instead of "os_key"
                profile_config["os_key"] = profile_config["os_type"].lower()

            self.config = profile_config
            self.is_loaded_profile = True  # Mark as loaded profile
            self.push_screen(
                ConfirmationScreen(self.config, allow_edit=True, os_images=self.os_images),
                self.handle_confirmation,
            )

    def handle_os_selection(self, result: dict[str, Any] | None) -> None:
        """Handle OS selection result."""
        if result:
            self.config.update(result)
            self.push_screen(
                DeviceSelectionScreen(self.os_images, result["os_key"], self.config),
                self.handle_device_selection,
            )
        else:
            # Go back to profile screen
            self.on_mount()

    def handle_device_selection(self, result: dict[str, Any] | None) -> None:
        """Handle device selection result."""
        if result:
            self.config.update(result)
            # Determine capabilities for dynamic screen flow
            os_key = self.config["os_key"]
            device_key = result["device_key"]
            self.push_screen(
                NetworkConfigScreen(os_key, device_key, self.device_properties, self.config),
                self.handle_network_config,
            )
        else:
            # Go back to OS selection
            self.push_screen(
                OSSelectionScreen(self.os_images, self.config), self.handle_os_selection
            )

    def handle_network_config(self, result: dict[str, Any] | None) -> None:
        """Handle network configuration result."""
        if result:
            self.config.update(result)
            os_key = self.config["os_key"]
            self.push_screen(SystemConfigScreen(os_key, self.config), self.handle_system_config)
        else:
            # Go back to device selection
            self.push_screen(
                DeviceSelectionScreen(self.os_images, self.config["os_key"], self.config),
                self.handle_device_selection,
            )

    def handle_system_config(self, result: dict[str, Any] | None) -> None:
        """Handle system configuration result."""
        if result:
            self.config.update(result)
            os_key = self.config["os_key"]
            device_key = self.config["device_key"]
            self.push_screen(
                AdvancedConfigScreen(
                    os_key, device_key, self.device_properties, self.os_properties, self.config
                ),
                self.handle_advanced_config,
            )
        else:
            # Go back to network config
            os_key = self.config["os_key"]
            device_key = self.config["device_key"]
            self.push_screen(
                NetworkConfigScreen(os_key, device_key, self.device_properties, self.config),
                self.handle_network_config,
            )

    def handle_advanced_config(self, result: dict[str, Any] | None) -> None:
        """Handle advanced configuration result."""
        if result:
            self.config.update(result)
            self.push_screen(BirdNETConfigScreen(self.config), self.handle_birdnet_config)
        else:
            # Go back to system config
            self.push_screen(
                SystemConfigScreen(self.config["os_key"], self.config), self.handle_system_config
            )

    def handle_birdnet_config(self, result: dict[str, Any] | None) -> None:
        """Handle BirdNET configuration result."""
        if result:
            self.config.update(result)
            self.push_screen(
                ConfirmationScreen(self.config, allow_edit=False, os_images=self.os_images),
                self.handle_confirmation,
            )
        else:
            # Go back to advanced config
            os_key = self.config["os_key"]
            device_key = self.config["device_key"]
            self.push_screen(
                AdvancedConfigScreen(
                    os_key, device_key, self.device_properties, self.os_properties, self.config
                ),
                self.handle_advanced_config,
            )

    def handle_confirmation(self, confirmed: bool) -> None:
        """Handle confirmation result."""
        if confirmed:
            if not self.is_loaded_profile:
                # Only ask to save for new configurations
                self.push_screen(
                    ProfileSaveScreen(self.config, self.loaded_profile_name),
                    self.handle_profile_save,
                )
            else:
                # Already saved profile, just exit
                self.exit(self.config)
        else:
            # User wants to edit - go back to start for full editing
            was_loaded = self.is_loaded_profile
            self.is_loaded_profile = False  # Editing makes it a new config
            # But keep the profile name for pre-filling save screen later
            if not was_loaded:
                self.loaded_profile_name = None
            # Start from OS selection with current config pre-filled
            self.push_screen(
                OSSelectionScreen(self.os_images, self.config), self.handle_os_selection
            )

    def handle_profile_save(self, saved: bool) -> None:
        """Handle profile save result."""
        # Whether saved or not, we're done
        self.exit(self.config)


# ============================================================================
# Profile Screens
# ============================================================================


class ProfileLoadScreen(ModalScreen[dict | None]):
    """Screen to load existing profile or start new."""

    def __init__(self) -> None:
        """Initialize screen."""
        super().__init__()
        self.profile_data: dict[str, dict[str, Any]] = {}
        self.profile_names: list[str] = []  # Map index to profile name

    def compose(self) -> ComposeResult:
        """Compose the profile loading screen."""
        profiles = ProfileManager.list_profiles()

        with Container(id="dialog"):
            yield Static("Load Configuration Profile", classes="screen-title")

            if profiles:
                # Build list items
                list_items = []

                # Add "New Configuration" option (index 0)
                self.profile_names.append("__new__")
                list_items.append(ListItem(Label("→ Start New Configuration")))

                # Add existing profiles with details
                for name in profiles:
                    config = ProfileManager.load_profile(name)
                    if config:
                        # Store config and name by index
                        self.profile_names.append(name)
                        self.profile_data[name] = config

                        # Build description
                        os_name = config.get("os_name", "Unknown OS")
                        device_name = config.get("device_name", "Unknown device")
                        hostname = config.get("hostname", "N/A")
                        wifi_ssid = config.get("wifi_ssid", "Not configured")

                        description = (
                            f"{name}\n"
                            f"  OS: {os_name} | Device: {device_name}\n"
                            f"  Hostname: {hostname} | WiFi: {wifi_ssid}"
                        )

                        list_items.append(ListItem(Label(description)))

                yield ListView(*list_items, id="profile_list")
                with Horizontal(classes="button-group"):
                    yield Button("Cancel", id="cancel", variant="error")
                    yield Button("Continue", id="continue", variant="primary")
            else:
                yield Static("\nNo saved profiles found. Starting new configuration.\n")
                yield Button("Continue", id="new", variant="primary")

    @on(Button.Pressed, "#continue")
    def handle_continue(self) -> None:
        """Handle continue button."""
        profile_list = self.query_one("#profile_list", ListView)
        if profile_list.index is None:
            self.notify("Please select a profile", severity="error")
            return

        # Get profile name by index
        selected_name = self.profile_names[profile_list.index]

        if selected_name == "__new__":
            self.dismiss(None)
        else:
            config = self.profile_data.get(selected_name)
            if config:
                # Return both config and profile name
                config["__profile_name__"] = selected_name
                self.dismiss(config)
            else:
                self.notify("Failed to load profile", severity="error")

    @on(Button.Pressed, "#new")
    def handle_new(self) -> None:
        """Handle new configuration button."""
        self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def handle_cancel(self) -> None:
        """Handle cancel button."""
        self.dismiss("CANCELLED")  # type: ignore[arg-type]


class ProfileSaveScreen(ModalScreen[bool]):
    """Screen to save current configuration as profile."""

    def __init__(self, config: dict[str, Any], initial_name: str | None = None) -> None:
        """Initialize with config to save and optional initial profile name."""
        super().__init__()
        self.config = config
        self.initial_name = initial_name

    def compose(self) -> ComposeResult:
        """Compose the profile save screen."""
        with Container(id="dialog"):
            yield Static("Save Configuration Profile", classes="screen-title")
            yield Input(
                id="profile_name",
                placeholder="Enter profile name...",
                value=self.initial_name or "",
                validators=[
                    Function(
                        lambda s: all(c.isalnum() or c in "_-" for c in s),
                        "Use letters, numbers, - or _",
                    )
                ],
            )
            with Horizontal(classes="button-group"):
                yield Button("Skip", id="skip", variant="default")
                yield Button("Save", id="save", variant="success")

    @on(Button.Pressed, "#save")
    def handle_save(self) -> None:
        """Handle save button."""
        name_input = self.query_one("#profile_name", Input)

        if not name_input.value:
            self.notify("Profile name required", severity="error")
            return

        if name_input.is_valid:
            ProfileManager.save_profile(name_input.value, self.config)
            self.notify(f"Profile '{name_input.value}' saved!", severity="information")
            self.dismiss(True)
        else:
            self.notify("Invalid profile name", severity="error")

    @on(Button.Pressed, "#skip")
    def handle_skip(self) -> None:
        """Handle skip button."""
        self.dismiss(False)


# Placeholder for other screens - will continue in next messages
class OSSelectionScreen(ModalScreen[dict | None]):
    """Screen for selecting the operating system."""

    def __init__(
        self, os_images: dict[str, Any], initial_config: dict[str, Any] | None = None
    ) -> None:
        """Initialize with OS images data and optional initial config."""
        super().__init__()
        self.os_images = os_images
        self.initial_config = initial_config or {}

    def compose(self) -> ComposeResult:
        """Compose the OS selection screen."""
        with Container(id="dialog"):
            yield Static("Step 1: Select Operating System", classes="screen-title")

            # Build options from os_images - use display name for both value and label
            # This ensures the Select dropdown shows only friendly names
            options = [(value["name"], value["name"]) for key, value in self.os_images.items()]

            # Pre-select OS if editing - use display text
            initial_value = Select.BLANK
            if self.initial_config:
                initial_os_key = self.initial_config.get("os_key", "").lower()
                if initial_os_key and initial_os_key in self.os_images:
                    initial_value = self.os_images[initial_os_key]["name"]

            yield Select(
                options=options,
                id="os_select",
                prompt="Choose operating system...",
                value=initial_value,
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        select = self.query_one("#os_select", Select)
        if select.value == Select.BLANK:
            self.notify("Please select an operating system", severity="error")
            return

        # Debug: Check what we're actually getting
        selected_value = str(select.value)

        # The Select widget returns the display text, not the key
        # We need to reverse-lookup the key from the display text
        os_key = None
        for key, os_info in self.os_images.items():
            if os_info["name"] == selected_value:
                os_key = key
                break

        if not os_key:
            self.notify(f"Invalid OS selection: {selected_value}", severity="error")
            return

        self.dismiss({"os_key": os_key})

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class DeviceSelectionScreen(ModalScreen[dict | None]):
    """Screen for selecting the target device."""

    def __init__(
        self, os_images: dict[str, Any], os_key: str, initial_config: dict[str, Any] | None = None
    ) -> None:
        """Initialize with OS images, selected OS, and optional initial config."""
        super().__init__()
        self.os_images = os_images
        self.os_key = os_key
        self.initial_config = initial_config or {}

    def compose(self) -> ComposeResult:
        """Compose the device selection screen."""
        with Container(id="dialog"):
            yield Static("Step 2: Select Target Device", classes="screen-title")

            # Build options from devices for selected OS
            # Use display name for both value and label to show only friendly names
            devices = self.os_images[self.os_key]["devices"]
            options = []
            for _key, value in devices.items():
                display_name = (
                    f"{value['name']}{' - ' + value.get('note', '') if value.get('note') else ''}"
                )
                options.append((display_name, display_name))

            # Pre-select device if editing - use display text
            initial_value = Select.BLANK
            if self.initial_config:
                initial_device_key = self.initial_config.get("device_key", "")
                if initial_device_key and initial_device_key in devices:
                    device_info = devices[initial_device_key]
                    note_suffix = f" - {device_info['note']}" if device_info.get("note") else ""
                    initial_value = f"{device_info['name']}{note_suffix}"

            yield Select(
                options=options,
                id="device_select",
                prompt="Choose target device...",
                value=initial_value,
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        select = self.query_one("#device_select", Select)
        if select.value == Select.BLANK:
            self.notify("Please select a device", severity="error")
            return

        # The Select widget returns the display text, not the key
        # We need to reverse-lookup the key from the display text
        selected_value = str(select.value)
        devices = self.os_images[self.os_key]["devices"]

        device_key = None
        for key, device_info in devices.items():
            # Match against the full display text (name + note if present)
            note_suffix = f" - {device_info['note']}" if device_info.get("note") else ""
            display_text = f"{device_info['name']}{note_suffix}"
            if display_text == selected_value:
                device_key = key
                break

        if not device_key:
            self.notify(f"Invalid device selection: {selected_value}", severity="error")
            return

        self.dismiss({"device_key": device_key})

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class NetworkConfigScreen(ModalScreen[dict | None]):
    """Screen for configuring network settings."""

    def __init__(
        self,
        os_key: str,
        device_key: str,
        device_properties: dict[str, Any],
        initial_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with OS/device info and optional initial config."""
        super().__init__()
        self.os_key = os_key
        self.device_key = device_key
        self.device_properties = device_properties
        self.initial_config = initial_config or {}

    def compose(self) -> ComposeResult:
        """Compose the network config screen."""
        with Container(id="dialog"):
            yield Static("Step 3: Network Configuration", classes="screen-title")

            # WiFi enable checkbox - pre-fill from config
            wifi_enabled = self.initial_config.get("enable_wifi", False)
            yield Checkbox("Enable WiFi", id="enable_wifi", value=wifi_enabled)

            # WiFi settings (conditionally enabled) - pre-fill from config
            yield Input(
                placeholder="WiFi SSID",
                id="wifi_ssid",
                value=self.initial_config.get("wifi_ssid", ""),
                disabled=not wifi_enabled,
            )
            yield Input(
                placeholder="WiFi Password",
                id="wifi_password",
                value=self.initial_config.get("wifi_password", ""),
                password=True,
                disabled=not wifi_enabled,
            )

            # WiFi auth - pre-select using display text
            wifi_auth_key = self.initial_config.get("wifi_auth", "WPA-PSK")
            auth_options = [
                ("WPA-PSK", "WPA-PSK (most common)"),
                ("WPA-EAP", "WPA-EAP (enterprise)"),
                ("OPEN", "OPEN (no security)"),
            ]
            # Find display text for the key
            wifi_auth_display = next(
                (display for key, display in auth_options if key == wifi_auth_key),
                "WPA-PSK (most common)",
            )

            yield Select(
                options=auth_options,
                id="wifi_auth",
                prompt="WiFi Authentication...",
                value=wifi_auth_display if wifi_enabled else Select.BLANK,
                disabled=not wifi_enabled,
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")

    @on(Checkbox.Changed, "#enable_wifi")
    def handle_wifi_toggle(self, event: Checkbox.Changed) -> None:
        """Enable/disable WiFi inputs based on checkbox."""
        ssid_input = self.query_one("#wifi_ssid", Input)
        password_input = self.query_one("#wifi_password", Input)
        auth_select = self.query_one("#wifi_auth", Select)

        ssid_input.disabled = not event.value
        password_input.disabled = not event.value
        auth_select.disabled = not event.value

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        wifi_enabled = self.query_one("#enable_wifi", Checkbox).value

        result: dict[str, Any] = {"enable_wifi": wifi_enabled}

        if wifi_enabled:
            ssid = self.query_one("#wifi_ssid", Input).value
            password = self.query_one("#wifi_password", Input).value
            auth_display = self.query_one("#wifi_auth", Select).value

            if not ssid:
                self.notify("WiFi SSID required when WiFi is enabled", severity="error")
                return

            # Reverse lookup: display text -> key
            auth_options = [
                ("WPA-PSK", "WPA-PSK (most common)"),
                ("WPA-EAP", "WPA-EAP (enterprise)"),
                ("OPEN", "OPEN (no security)"),
            ]
            auth_key = next(
                (key for key, display in auth_options if display == str(auth_display)), "WPA-PSK"
            )

            result.update({"wifi_ssid": ssid, "wifi_password": password, "wifi_auth": auth_key})

        self.dismiss(result)

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class SystemConfigScreen(ModalScreen[dict | None]):
    """Screen for configuring system settings."""

    def __init__(self, os_key: str, initial_config: dict[str, Any] | None = None) -> None:
        """Initialize with OS key and optional initial config."""
        super().__init__()
        self.os_key = os_key
        self.is_dietpi = os_key.lower().startswith("dietpi")
        self.initial_config = initial_config or {}

    def compose(self) -> ComposeResult:
        """Compose the system config screen."""
        with Container(id="dialog"):
            yield Static("Step 4: System Configuration", classes="screen-title")

            # Hostname - pre-fill from config
            yield Input(
                placeholder="Hostname (e.g., birdnetpi)",
                id="hostname",
                value=self.initial_config.get("hostname", ""),
                validators=[HostnameValidator()],
            )

            # Username (disabled for DietPi) - pre-fill from config
            if self.is_dietpi:
                yield Static("Username: root (DietPi default)", classes="info-label")
            else:
                yield Input(
                    placeholder="Username",
                    id="username",
                    value=self.initial_config.get("username", "birdnet"),
                )

            # Password - pre-fill from config
            yield Input(
                placeholder="Password",
                id="password",
                value=self.initial_config.get("password", ""),
                password=True,
                validators=[PasswordValidator()],
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        hostname_input = self.query_one("#hostname", Input)
        password_input = self.query_one("#password", Input)

        # Validate hostname
        if not hostname_input.is_valid or not hostname_input.value:
            self.notify("Valid hostname required", severity="error")
            return

        # Validate password
        if not password_input.is_valid or not password_input.value:
            self.notify("Valid password required", severity="error")
            return

        result: dict[str, Any] = {
            "hostname": hostname_input.value,
            "password": password_input.value,
        }

        # Add username for non-DietPi
        if not self.is_dietpi:
            username_input = self.query_one("#username", Input)
            if not username_input.value:
                self.notify("Username required", severity="error")
                return
            result["username"] = username_input.value
        else:
            result["username"] = "root"

        self.dismiss(result)

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class AdvancedConfigScreen(ModalScreen[dict | None]):
    """Screen for advanced configuration options."""

    def __init__(
        self,
        os_key: str,
        device_key: str,
        device_properties: dict[str, Any],
        os_properties: dict[str, Any],
        initial_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with OS/device info and optional initial config."""
        super().__init__()
        self.os_key = os_key
        self.device_key = device_key
        self.device_properties = device_properties
        self.os_properties = os_properties
        self.initial_config = initial_config or {}

        # Get combined capabilities (OS + device)
        # This checks both: OS has SPI config method AND device has SPI hardware
        # For example: Pi 4 + Raspberry Pi OS = True (config_txt method + has_spi)
        #             Pi 4 + Armbian = False (no SPI config method for Armbian yet)
        capabilities = get_combined_capabilities(
            os_key, device_key, os_properties, device_properties
        )
        self.supports_spi = capabilities.get("supports_spi", False)

    def compose(self) -> ComposeResult:
        """Compose the advanced config screen."""
        with Container(id="dialog"):
            yield Static("Step 5: Advanced Configuration", classes="screen-title")

            # Copy installer checkbox - pre-fill from config
            yield Checkbox(
                "Preserve installer to /root/ after first boot",
                id="copy_installer",
                value=self.initial_config.get("copy_installer", False),
            )

            # Enable SPI checkbox (conditional on device support) - pre-fill from config
            if self.supports_spi:
                yield Checkbox(
                    "Enable SPI (Required for GPIO-wired displays)",
                    id="enable_spi",
                    value=self.initial_config.get("enable_spi", False),
                )
            else:
                yield Static("SPI: Not supported on this device", classes="info-label")

            # GPIO debug checkbox - pre-fill from config
            yield Checkbox(
                "Enable GPIO debugging output",
                id="gpio_debug",
                value=self.initial_config.get("gpio_debug", False),
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        result: dict[str, Any] = {
            "copy_installer": self.query_one("#copy_installer", Checkbox).value,
            "gpio_debug": self.query_one("#gpio_debug", Checkbox).value,
        }

        # Add SPI setting if device supports it
        if self.supports_spi:
            result["enable_spi"] = self.query_one("#enable_spi", Checkbox).value
        else:
            result["enable_spi"] = False

        self.dismiss(result)

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class BirdNETConfigScreen(ModalScreen[dict | None]):
    """Screen for optional BirdNET-Pi configuration."""

    def __init__(self, initial_config: dict[str, Any] | None = None) -> None:
        """Initialize with optional initial config."""
        super().__init__()
        self.initial_config = initial_config or {}

    def compose(self) -> ComposeResult:
        """Compose the BirdNET config screen."""
        with Container(id="dialog"):
            yield Static("Step 6: BirdNET-Pi Configuration (Optional)", classes="screen-title")
            yield Static(
                "These settings can be configured later through the web interface.",
                classes="info-value",
            )

            # Advanced install options (for developers/testers)
            yield Static("Advanced Options (for developers):", classes="info-label")

            # Repository URL - pre-fill from config
            yield Input(
                placeholder="Repository URL (optional, for testing branches)",
                id="repo_url",
                value=self.initial_config.get("repo_url", ""),
            )

            # Branch name - pre-fill from config
            yield Input(
                placeholder="Branch name (optional, default: main)",
                id="branch",
                value=self.initial_config.get("branch", ""),
            )

            yield Static("BirdNET-Pi Configuration:", classes="info-label")

            # Device name - pre-fill from config
            yield Input(
                placeholder="Device name (optional)",
                id="device_name",
                value=self.initial_config.get("device_name", ""),
            )

            # Location - pre-fill from config
            lat_value = (
                str(self.initial_config.get("latitude", ""))
                if self.initial_config.get("latitude") is not None
                else ""
            )
            lon_value = (
                str(self.initial_config.get("longitude", ""))
                if self.initial_config.get("longitude") is not None
                else ""
            )

            yield Input(
                placeholder="Latitude (optional, e.g., 45.5231)",
                id="latitude",
                value=lat_value,
                validators=[LatitudeValidator()],
            )
            yield Input(
                placeholder="Longitude (optional, e.g., -122.6765)",
                id="longitude",
                value=lon_value,
                validators=[LongitudeValidator()],
            )

            # Timezone selection - pre-select using display text
            common_timezones = [
                ("America/New_York", "America/New_York (ET)"),
                ("America/Chicago", "America/Chicago (CT)"),
                ("America/Denver", "America/Denver (MT)"),
                ("America/Los_Angeles", "America/Los_Angeles (PT)"),
                ("America/Anchorage", "America/Anchorage (AKT)"),
                ("Pacific/Honolulu", "Pacific/Honolulu (HST)"),
                ("Europe/London", "Europe/London (GMT)"),
                ("Europe/Paris", "Europe/Paris (CET)"),
                ("Asia/Tokyo", "Asia/Tokyo (JST)"),
                ("Australia/Sydney", "Australia/Sydney (AEST)"),
            ]
            timezone_key = self.initial_config.get("timezone", "")
            timezone_display = (
                next(
                    (display for key, display in common_timezones if key == timezone_key),
                    Select.BLANK,
                )
                if timezone_key
                else Select.BLANK
            )

            yield Select(
                options=common_timezones,
                id="timezone",
                prompt="Timezone (optional)...",
                value=timezone_display,
            )

            # Language selection - pre-select using display text
            languages = [
                ("en", "English"),
                ("de", "German (Deutsch)"),
                ("fr", "French (Français)"),
                ("es", "Spanish (Español)"),
                ("pt", "Portuguese (Português)"),
                ("it", "Italian (Italiano)"),
                ("nl", "Dutch (Nederlands)"),
                ("ja", "Japanese (日本語)"),
                ("zh", "Chinese (中文)"),
            ]
            language_key = self.initial_config.get("language", "")
            language_display = (
                next((display for key, display in languages if key == language_key), Select.BLANK)
                if language_key
                else Select.BLANK
            )

            yield Select(
                options=languages,
                id="language",
                prompt="Language (optional)...",
                value=language_display,
            )

            with Horizontal(classes="button-group"):
                yield Button("Back", id="back")
                yield Button("Continue", id="continue", variant="primary")

    @on(Button.Pressed, "#continue")
    def handle_continue(self) -> None:  # noqa: C901
        """Handle continue button."""
        result: dict[str, Any] = {}

        # Advanced install options
        repo_url = self.query_one("#repo_url", Input).value
        if repo_url:
            result["birdnet_repo_url"] = repo_url

        branch = self.query_one("#branch", Input).value
        if branch:
            result["birdnet_branch"] = branch

        # Device name
        device_name = self.query_one("#device_name", Input).value
        if device_name:
            result["device_name"] = device_name

        # Latitude/Longitude
        lat_input = self.query_one("#latitude", Input)
        lon_input = self.query_one("#longitude", Input)

        if lat_input.value or lon_input.value:
            # Validate both are provided if either is
            if not (lat_input.value and lon_input.value):
                self.notify("Both latitude and longitude must be provided", severity="error")
                return

            # Validate they're valid
            if not (lat_input.is_valid and lon_input.is_valid):
                self.notify("Invalid latitude or longitude", severity="error")
                return

            result["latitude"] = float(lat_input.value)
            result["longitude"] = float(lon_input.value)

        # Timezone - reverse lookup display text -> key
        timezone_display = self.query_one("#timezone", Select).value
        if timezone_display != Select.BLANK:
            common_timezones = [
                ("America/New_York", "America/New_York (ET)"),
                ("America/Chicago", "America/Chicago (CT)"),
                ("America/Denver", "America/Denver (MT)"),
                ("America/Los_Angeles", "America/Los_Angeles (PT)"),
                ("America/Anchorage", "America/Anchorage (AKT)"),
                ("Pacific/Honolulu", "Pacific/Honolulu (HST)"),
                ("Europe/London", "Europe/London (GMT)"),
                ("Europe/Paris", "Europe/Paris (CET)"),
                ("Asia/Tokyo", "Asia/Tokyo (JST)"),
                ("Australia/Sydney", "Australia/Sydney (AEST)"),
            ]
            timezone_key = next(
                (key for key, display in common_timezones if display == str(timezone_display)), None
            )
            if timezone_key:
                result["timezone"] = timezone_key

        # Language - reverse lookup display text -> key
        language_display = self.query_one("#language", Select).value
        if language_display != Select.BLANK:
            languages = [
                ("en", "English"),
                ("de", "German (Deutsch)"),
                ("fr", "French (Français)"),
                ("es", "Spanish (Español)"),
                ("pt", "Portuguese (Português)"),
                ("it", "Italian (Italiano)"),
                ("nl", "Dutch (Nederlands)"),
                ("ja", "Japanese (日本語)"),
                ("zh", "Chinese (中文)"),
            ]
            language_key = next(
                (key for key, display in languages if display == str(language_display)), None
            )
            if language_key:
                result["language"] = language_key

        self.dismiss(result)

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(None)


class ConfirmationScreen(ModalScreen[bool]):
    """Screen to review and confirm configuration."""

    def __init__(
        self,
        config: dict[str, Any],
        allow_edit: bool = False,
        os_images: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with config to confirm."""
        super().__init__()
        self.config = config
        self.allow_edit = allow_edit
        self.os_images = os_images or {}

    def compose(self) -> ComposeResult:  # noqa: C901
        """Compose the confirmation screen."""
        with Container(id="dialog"):
            yield Static("Confirm Configuration", classes="screen-title")

            # Build configuration summary
            with Vertical(classes="config-table"):
                # OS and Device - use display names from OS_IMAGES
                os_key = self.config.get("os_key", "")
                device_key = self.config.get("device_key", "")

                # Get OS display name
                os_name = "N/A"
                if os_key and self.os_images:
                    os_name = self.os_images.get(os_key, {}).get("name", os_key)
                elif os_key:
                    os_name = os_key

                # Get device display name
                device_name = "N/A"
                if os_key and device_key and self.os_images:
                    device_name = (
                        self.os_images.get(os_key, {})
                        .get("devices", {})
                        .get(device_key, {})
                        .get("name", device_key)
                    )
                elif device_key:
                    device_name = device_key

                with Horizontal(classes="config-row"):
                    yield Static("Operating System:", classes="config-key")
                    yield Static(os_name, classes="config-value")
                with Horizontal(classes="config-row"):
                    yield Static("Target Device:", classes="config-key")
                    yield Static(device_name, classes="config-value")

                # Network
                if self.config.get("enable_wifi"):
                    with Horizontal(classes="config-row"):
                        yield Static("WiFi SSID:", classes="config-key")
                        yield Static(self.config.get("wifi_ssid", ""), classes="config-value")
                    with Horizontal(classes="config-row"):
                        yield Static("WiFi Auth:", classes="config-key")
                        yield Static(
                            self.config.get("wifi_auth", "WPA-PSK"), classes="config-value"
                        )
                else:
                    with Horizontal(classes="config-row"):
                        yield Static("WiFi:", classes="config-key")
                        yield Static("Disabled (Ethernet only)", classes="config-value")

                # System
                with Horizontal(classes="config-row"):
                    yield Static("Hostname:", classes="config-key")
                    yield Static(self.config.get("hostname", ""), classes="config-value")
                with Horizontal(classes="config-row"):
                    yield Static("Username:", classes="config-key")
                    yield Static(self.config.get("username", ""), classes="config-value")

                # Advanced
                with Horizontal(classes="config-row"):
                    yield Static("Preserve Installer:", classes="config-key")
                    yield Static(
                        "Yes" if self.config.get("copy_installer") else "No", classes="config-value"
                    )
                with Horizontal(classes="config-row"):
                    yield Static("Enable SPI:", classes="config-key")
                    yield Static(
                        "Yes" if self.config.get("enable_spi") else "No", classes="config-value"
                    )
                with Horizontal(classes="config-row"):
                    yield Static("GPIO Debug:", classes="config-key")
                    yield Static(
                        "Yes" if self.config.get("gpio_debug") else "No", classes="config-value"
                    )

                # BirdNET (optional fields)
                if self.config.get("device_name"):
                    with Horizontal(classes="config-row"):
                        yield Static("Device Name:", classes="config-key")
                        yield Static(self.config["device_name"], classes="config-value")
                if self.config.get("latitude") is not None:
                    with Horizontal(classes="config-row"):
                        yield Static("Location:", classes="config-key")
                        yield Static(
                            f"{self.config['latitude']}, {self.config['longitude']}",
                            classes="config-value",
                        )
                if self.config.get("timezone"):
                    with Horizontal(classes="config-row"):
                        yield Static("Timezone:", classes="config-key")
                        yield Static(self.config["timezone"], classes="config-value")
                if self.config.get("language"):
                    with Horizontal(classes="config-row"):
                        yield Static("Language:", classes="config-key")
                        yield Static(self.config["language"], classes="config-value")

            with Horizontal(classes="button-group"):
                if self.allow_edit:
                    yield Button("Edit", id="edit")
                else:
                    yield Button("Back", id="back")
                yield Button("Confirm", id="confirm", variant="success")

    @on(Button.Pressed, "#confirm")
    def handle_confirm(self) -> None:
        """Handle confirm button."""
        self.dismiss(True)

    @on(Button.Pressed, "#back")
    def handle_back(self) -> None:
        """Handle back button."""
        self.dismiss(False)

    @on(Button.Pressed, "#edit")
    def handle_edit(self) -> None:
        """Handle edit button."""
        self.dismiss(False)


# ============================================================================
# Device Selection Screens
# ============================================================================


class DeviceSelectionForFlashScreen(ModalScreen[dict | None]):
    """Screen for selecting the SD card/block device to flash."""

    def __init__(self, devices: list[dict[str, Any]]) -> None:
        """Initialize with list of available block devices."""
        super().__init__()
        self.devices = devices

    def compose(self) -> ComposeResult:
        """Compose the device selection screen."""
        with Container(id="dialog"):
            yield Static("Select SD Card to Flash", classes="screen-title")

            if not self.devices:
                yield Static(
                    "⚠️  No removable devices found!\n\nPlease insert an SD card and try again.",
                    classes="info-section",
                )
                with Horizontal(classes="button-group"):
                    yield Button("Cancel", id="cancel", variant="error")
            else:
                yield Static("Available removable devices:", classes="info-label")

                # Build device list
                with ListView(id="device_list"):
                    for _idx, device in enumerate(self.devices):
                        device_text = (
                            f"{device['device']}\n  Size: {device['size']} | Type: {device['type']}"
                        )
                        yield ListItem(Label(device_text))

                with Horizontal(classes="button-group"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Next", id="next", variant="primary")

    @on(Button.Pressed, "#next")
    def handle_next(self) -> None:
        """Handle next button."""
        device_list = self.query_one("#device_list", ListView)
        if device_list.index is None:
            self.notify("Please select a device", severity="error")
            return

        selected = self.devices[device_list.index]
        self.dismiss(selected)

    @on(Button.Pressed, "#cancel")
    def handle_cancel(self) -> None:
        """Handle cancel button."""
        self.dismiss(None)


class ConfirmFlashScreen(ModalScreen[bool]):
    """Screen to confirm the destructive flash operation."""

    def __init__(self, device_path: str) -> None:
        """Initialize with device path to flash."""
        super().__init__()
        self.device_path = device_path

    def compose(self) -> ComposeResult:
        """Compose the confirmation screen."""
        with Container(id="dialog"):
            yield Static("⚠️  CONFIRM FLASH OPERATION", classes="screen-title")

            yield Static(
                f"WARNING: ALL DATA ON {self.device_path} WILL BE PERMANENTLY ERASED!\n\n"
                "This action cannot be undone.\n\n"
                "Are you absolutely sure you want to continue?",
                classes="info-section",
            )

            with Horizontal(classes="button-group"):
                yield Button("Cancel", id="cancel", variant="error")
                yield Button("Yes, Flash Device", id="confirm", variant="success")

    @on(Button.Pressed, "#confirm")
    def handle_confirm(self) -> None:
        """Handle confirm button."""
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def handle_cancel(self) -> None:
        """Handle cancel button."""
        self.dismiss(False)


# ============================================================================
# Device Selection Wizard App
# ============================================================================


class DeviceSelectionApp(App[dict | None]):
    """Standalone TUI for selecting a device to flash.

    This runs after configuration is complete to select the physical device.
    """

    CSS_PATH = "flasher.tcss"

    def __init__(self, devices: list[dict[str, Any]]) -> None:
        """Initialize with list of available devices."""
        super().__init__()
        self.devices = devices
        self.selected_device: dict[str, Any] | None = None

    def on_mount(self) -> None:
        """Start with device selection."""
        self.push_screen(DeviceSelectionForFlashScreen(self.devices), self.handle_device_selection)

    def handle_device_selection(self, device: dict[str, Any] | None) -> None:
        """Handle device selection result."""
        if device is None:
            # User cancelled
            self.exit(None)
        else:
            # Show confirmation
            self.selected_device = device
            self.push_screen(
                ConfirmFlashScreen(device["device"]),
                self.handle_confirmation,
            )

    def handle_confirmation(self, confirmed: bool) -> None:
        """Handle flash confirmation."""
        if confirmed:
            # Return the selected device
            self.exit(self.selected_device)
        else:
            # User cancelled
            self.exit(None)
