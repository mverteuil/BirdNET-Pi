#!/usr/bin/env python3
"""Patch Waveshare ePaper library to support Orange Pi.

This script modifies the epdconfig.py file to:
1. Add Orange Pi detection via /proc/device-tree/model
2. Add OrangePi class using lgpio for GPIO control
3. Update hardware detection logic to use OrangePi class when detected
"""

import sys
from pathlib import Path

ORANGEPI_CLASS = '''
class OrangePi:
    """Orange Pi GPIO implementation using lgpio.

    Uses the same pin definitions as Raspberry Pi for 40-pin header compatibility.
    """
    # Pin definition (same as Raspberry Pi for 40-pin header compatibility)
    RST_PIN  = 17
    DC_PIN   = 25
    CS_PIN   = 8
    BUSY_PIN = 24
    PWR_PIN  = 18
    MOSI_PIN = 10
    SCLK_PIN = 11

    def __init__(self):
        import spidev
        import lgpio

        # Use gpiochip4 for Orange Pi 5 (40-pin header)
        self.chip = lgpio.gpiochip_open(4)

        # Free pins if already claimed from previous tests
        for pin in [self.RST_PIN, self.DC_PIN, self.PWR_PIN, self.BUSY_PIN]:
            try:
                lgpio.gpio_free(self.chip, pin)
            except:
                pass

        lgpio.gpio_claim_output(self.chip, self.RST_PIN)
        lgpio.gpio_claim_output(self.chip, self.DC_PIN)
        lgpio.gpio_claim_output(self.chip, self.PWR_PIN)
        lgpio.gpio_claim_input(self.chip, self.BUSY_PIN)

        self.SPI = spidev.SpiDev()

    def digital_write(self, pin, value):
        import lgpio
        lgpio.gpio_write(self.chip, pin, 1 if value else 0)

    def digital_read(self, pin):
        import lgpio
        return lgpio.gpio_read(self.chip, pin)

    def delay_ms(self, delaytime):
        import time
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.writebytes(data)

    def spi_writebyte2(self, data):
        self.SPI.writebytes2(data)

    def module_init(self, cleanup=False):
        import lgpio
        lgpio.gpio_write(self.chip, self.PWR_PIN, 1)

        # SPI device, bus = 4, device = 0 (Orange Pi 5 uses SPI4)
        self.SPI.open(4, 0)
        self.SPI.max_speed_hz = 4000000
        self.SPI.mode = 0b00
        return 0

    def module_exit(self, cleanup=False):
        import lgpio
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("spi end")
        self.SPI.close()

        lgpio.gpio_write(self.chip, self.RST_PIN, 0)
        lgpio.gpio_write(self.chip, self.DC_PIN, 0)
        lgpio.gpio_write(self.chip, self.PWR_PIN, 0)
        logger.debug("close 5V, Module enters 0 power consumption ...")

        if cleanup:
            lgpio.gpiochip_close(self.chip)

'''


def patch_epdconfig(filepath: Path) -> bool:
    """Patch epdconfig.py to add Orange Pi support.

    Args:
        filepath: Path to epdconfig.py

    Returns:
        True if patching succeeded, False otherwise
    """
    if not filepath.exists():
        print(f"Error: {filepath} not found")
        return False

    # Read the file
    content = filepath.read_text()

    # Check if already patched
    if "class OrangePi:" in content:
        print("Already patched - skipping")
        return True

    # 1. Add device tree model check for Orange Pi detection
    old_detection = """output, _ = process.communicate()
if sys.version_info[0] == 2:
    output = output.decode(sys.stdout.encoding)

if "Raspberry" in output:"""

    new_detection = """output, _ = process.communicate()
if sys.version_info[0] == 2:
    output = output.decode(sys.stdout.encoding)

# Also check device tree model for Orange Pi
if os.path.exists("/proc/device-tree/model"):
    with open("/proc/device-tree/model", "r") as f:
        output += f.read()

if "Raspberry" in output:"""

    if old_detection in content:
        content = content.replace(old_detection, new_detection)
        print("✓ Added Orange Pi detection")
    else:
        print("Warning: Could not find detection code to patch")

    # 2. Add OrangePi class before RaspberryPi class
    content = content.replace("class RaspberryPi:", ORANGEPI_CLASS + "class RaspberryPi:")
    print("✓ Added OrangePi class")

    # 3. Update hardware selection logic
    old_selection = """if "Raspberry" in output:
    implementation = RaspberryPi()"""

    new_selection = """if "Raspberry" in output:
    implementation = RaspberryPi()
elif "Orange Pi" in output:
    implementation = OrangePi()"""

    if old_selection in content:
        content = content.replace(old_selection, new_selection)
        print("✓ Updated hardware selection logic")
    else:
        print("Warning: Could not find hardware selection code to patch")

    # Write back
    filepath.write_text(content)
    print(f"✓ Successfully patched {filepath}")
    return True


def main() -> int:
    """Run the Waveshare ePaper Orange Pi patcher."""
    if len(sys.argv) != 2:
        print("Usage: patch_waveshare_orangepi.py <path_to_epdconfig.py>")
        print("Example: patch_waveshare_orangepi.py <waveshare_lib>/epdconfig.py")
        return 1

    filepath = Path(sys.argv[1])
    success = patch_epdconfig(filepath)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
