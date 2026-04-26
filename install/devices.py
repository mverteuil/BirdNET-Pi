"""Device and OS configuration models for SD card flashing.

This module defines the hardware and operating system characteristics needed
for automated SD card preparation.
"""

from dataclasses import dataclass
from enum import Enum


class ChipFamily(str, Enum):
    """SoC chip families."""

    BCM2711 = "bcm2711"  # Raspberry Pi 4
    BCM2712 = "bcm2712"  # Raspberry Pi 5
    RK3588 = "rk3588"  # Rockchip (Orange Pi 5 series, ROCK 5B)
    H618 = "h618"  # Allwinner (Orange Pi Zero 2W)
    S905X = "s905x"  # Amlogic (Le Potato)


@dataclass(frozen=True)
class DeviceSpec:
    """Hardware device specification."""

    key: str  # Internal identifier (e.g., "orange_pi_5_pro")
    name: str  # Human-readable name (e.g., "Orange Pi 5 Pro")
    chip: ChipFamily
    has_wifi: bool
    has_spi: bool

    # OS-specific boot partition paths
    # Key: os_key, Value: boot partition mount point
    boot_partitions: dict[str, str]

    # SPI overlay names for enabling ePaper HAT
    # Key: os_key, Value: overlay name
    spi_overlays: dict[str, str | None]


@dataclass(frozen=True)
class ImageSource:
    """OS image download source."""

    url: str
    sha256: str | None = None  # Optional checksum
    is_armbian: bool = False  # Special handling for Armbian redirects
    is_dietpi: bool = False  # Special handling for DietPi


@dataclass(frozen=True)
class OSSpec:
    """Operating system specification."""

    key: str  # Internal identifier (e.g., "dietpi", "raspbian")
    name: str  # Human-readable name (e.g., "DietPi", "Raspberry Pi OS")

    # Image URLs by device
    # Key: device_key, Value: ImageSource
    images: dict[str, ImageSource]


# Device definitions
DEVICES: dict[str, DeviceSpec] = {
    # Raspberry Pi devices
    "pi_zero2w": DeviceSpec(
        key="pi_zero2w",
        name="Raspberry Pi Zero 2 W",
        chip=ChipFamily.BCM2711,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "raspbian": "/boot/firmware",
            "dietpi": "/boot/firmware",
        },
        spi_overlays={
            "raspbian": None,  # dtparam=spi=on in config.txt
            "dietpi": None,  # dtparam=spi=on in config.txt
        },
    ),
    "pi_3": DeviceSpec(
        key="pi_3",
        name="Raspberry Pi 3",
        chip=ChipFamily.BCM2711,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "raspbian": "/boot/firmware",
            "dietpi": "/boot/firmware",
        },
        spi_overlays={
            "raspbian": None,
            "dietpi": None,
        },
    ),
    "pi_4": DeviceSpec(
        key="pi_4",
        name="Raspberry Pi 4",
        chip=ChipFamily.BCM2711,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "raspbian": "/boot/firmware",
            "dietpi": "/boot/firmware",
        },
        spi_overlays={
            "raspbian": None,
            "dietpi": None,
        },
    ),
    "pi_5": DeviceSpec(
        key="pi_5",
        name="Raspberry Pi 5",
        chip=ChipFamily.BCM2712,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "raspbian": "/boot/firmware",
            "dietpi": "/boot/firmware",
        },
        spi_overlays={
            "raspbian": None,
            "dietpi": None,
        },
    ),
    # Orange Pi devices
    "orange_pi_0w2": DeviceSpec(
        key="orange_pi_0w2",
        name="Orange Pi Zero 2W",
        chip=ChipFamily.H618,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "armbian": "/boot",
            "dietpi": "/boot",
        },
        spi_overlays={
            "armbian": "spi-spidev",  # Allwinner H618
            "dietpi": "spi-spidev",
        },
    ),
    "orange_pi_5_plus": DeviceSpec(
        key="orange_pi_5_plus",
        name="Orange Pi 5 Plus",
        chip=ChipFamily.RK3588,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "armbian": "/boot",
            "dietpi": "/boot",
        },
        spi_overlays={
            "armbian": "rk3588-spi4-m0-cs1-spidev",  # RK3588
            "dietpi": "rk3588-spi4-m0-cs1-spidev",
        },
    ),
    "orange_pi_5_pro": DeviceSpec(
        key="orange_pi_5_pro",
        name="Orange Pi 5 Pro",
        chip=ChipFamily.RK3588,
        has_wifi=True,
        has_spi=True,
        boot_partitions={
            "armbian": "/boot",
            "dietpi": "/boot",  # DIETPISETUP partition at /boot, not /boot/firmware
        },
        spi_overlays={
            "armbian": "rk3588-spi4-m0-cs1-spidev",
            "dietpi": "rk3588-spi4-m0-cs1-spidev",
        },
    ),
    # Other devices
    "le_potato": DeviceSpec(
        key="le_potato",
        name="Libre Computer Le Potato",
        chip=ChipFamily.S905X,
        has_wifi=False,
        has_spi=True,
        boot_partitions={
            "armbian": "/boot",
            "dietpi": "/boot",
        },
        spi_overlays={
            "armbian": None,  # TODO: Verify SPI overlay for Amlogic
            "dietpi": None,
        },
    ),
    "rock_5b": DeviceSpec(
        key="rock_5b",
        name="Radxa ROCK 5B",
        chip=ChipFamily.RK3588,
        has_wifi=False,
        has_spi=True,
        boot_partitions={
            "armbian": "/boot",
            "dietpi": "/boot",
        },
        spi_overlays={
            "armbian": "rk3588-spi1-m1-cs0-spidev",  # Alternative: spi3-m1
            "dietpi": "rk3588-spi1-m1-cs0-spidev",
        },
    ),
}


# Operating system definitions
OPERATING_SYSTEMS: dict[str, OSSpec] = {
    "raspbian": OSSpec(
        key="raspbian",
        name="Raspberry Pi OS",
        images={
            "pi_zero2w": ImageSource(
                url="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                sha256="3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
            ),
            "pi_3": ImageSource(
                url="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                sha256="3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
            ),
            "pi_4": ImageSource(
                url="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                sha256="3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
            ),
            "pi_5": ImageSource(
                url="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz",
                sha256="3e8d1d7166aa832aded24e90484d83f4e8ad594b5a33bb4a9a1ff3ac0ac84d92",
            ),
        },
    ),
    "armbian": OSSpec(
        key="armbian",
        name="Armbian",
        images={
            "orange_pi_0w2": ImageSource(
                url="https://dl.armbian.com/orangepizero2w/Bookworm_current_minimal",
                is_armbian=True,
            ),
            "orange_pi_5_plus": ImageSource(
                url="https://dl.armbian.com/orangepi5-plus/Bookworm_current_minimal",
                is_armbian=True,
            ),
            "orange_pi_5_pro": ImageSource(
                url="https://dl.armbian.com/orangepi5pro/Trixie_vendor_minimal",
                is_armbian=True,
            ),
            "rock_5b": ImageSource(
                url="https://dl.armbian.com/rock-5b/Bookworm_current_minimal",
                is_armbian=True,
            ),
            "le_potato": ImageSource(
                url="https://dl.armbian.com/lepotato/Bookworm_current_minimal",
                is_armbian=True,
            ),
        },
    ),
    "dietpi": OSSpec(
        key="dietpi",
        name="DietPi",
        images={
            "pi_zero2w": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_RPiZero2W-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "pi_3": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_RPi3-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "pi_4": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_RPi4-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "pi_5": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_RPi5-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "orange_pi_0w2": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_OrangePiZero2W-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "orange_pi_5_plus": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_OrangePi5Plus-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "orange_pi_5_pro": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_OrangePi5Pro-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "rock_5b": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_ROCK5B-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
            "le_potato": ImageSource(
                url="https://dietpi.com/downloads/images/DietPi_LePotato-ARMv8-Bookworm.img.xz",
                is_dietpi=True,
            ),
        },
    ),
}


def get_boot_partition(device_key: str, os_key: str) -> str:
    """Get the boot partition mount point for a device/OS combination.

    Args:
        device_key: Device identifier (e.g., "orange_pi_5_pro")
        os_key: OS identifier (e.g., "dietpi")

    Returns:
        Boot partition path (e.g., "/boot" or "/boot/firmware")

    Raises:
        KeyError: If device or OS combination is not supported
    """
    device = DEVICES[device_key]
    return device.boot_partitions[os_key]


def get_spi_overlay(device_key: str, os_key: str) -> str | None:
    """Get the SPI overlay name for a device/OS combination.

    Args:
        device_key: Device identifier
        os_key: OS identifier

    Returns:
        SPI overlay name, or None if handled via config.txt dtparam

    Raises:
        KeyError: If device or OS combination is not supported
    """
    device = DEVICES[device_key]
    return device.spi_overlays[os_key]


def get_capabilities(device_key: str) -> dict[str, bool]:
    """Get hardware capabilities for a device.

    Args:
        device_key: Device identifier

    Returns:
        Dictionary with capability flags (has_wifi, has_spi)

    Raises:
        KeyError: If device is not supported
    """
    device = DEVICES[device_key]
    return {
        "has_wifi": device.has_wifi,
        "has_spi": device.has_spi,
    }


def build_os_images_dict() -> dict[str, dict]:
    """Build legacy OS_IMAGES dictionary structure for TUI compatibility.

    Returns:
        Dictionary in format: {os_key: {"name": str, "devices": {device_key: {...}}}}
    """
    os_images = {}

    for os_key, os_spec in OPERATING_SYSTEMS.items():
        devices_dict = {}
        for device_key in os_spec.images.keys():
            device_spec = DEVICES[device_key]
            image_source = os_spec.images[device_key]

            devices_dict[device_key] = {
                "name": device_spec.name,
                "url": image_source.url,
                "sha256": image_source.sha256,
                "is_armbian": image_source.is_armbian,
                "is_dietpi": image_source.is_dietpi,
            }

        os_images[os_key] = {
            "name": os_spec.name,
            "devices": devices_dict,
        }

    return os_images
