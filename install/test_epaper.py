#!/usr/bin/env python3
"""Test script for Waveshare e-Paper HAT.

This script verifies that the ePaper HAT is properly connected and working.
Can be run standalone without installing the full BirdNET-Pi system.
"""

import sys
import time
from pathlib import Path


def check_spi_devices() -> bool:
    """Check if SPI devices are available."""
    print("=" * 50)
    print("Checking SPI devices...")
    print("=" * 50)

    spi_devices = list(Path("/dev").glob("spidev*"))
    if not spi_devices:
        print("❌ No SPI devices found!")
        print("   SPI may not be enabled in /boot/firmware/config.txt")
        print("   Add or uncomment: dtparam=spi=on")
        print("   Then reboot and try again.")
        return False

    print(f"✓ Found {len(spi_devices)} SPI device(s):")
    for device in spi_devices:
        print(f"  - {device}")
    return True


def check_waveshare_module() -> bool:
    """Check if waveshare_epd module is available."""
    print("\n" + "=" * 50)
    print("Checking waveshare_epd Python module...")
    print("=" * 50)

    try:
        import waveshare_epd  # noqa: F401

        print("✓ waveshare_epd module is installed")
        return True
    except ImportError:
        print("❌ waveshare_epd module not found!")
        print("   Install with: uv sync --extra epaper")
        print("   Or: pip install waveshare-epd")
        return False


def detect_display_model() -> tuple[object | None, str | None]:
    """Try to detect which ePaper display model is connected."""
    print("\n" + "=" * 50)
    print("Detecting display model...")
    print("=" * 50)

    # Common Waveshare ePaper display models
    models = [
        "epd2in13_V4",  # 2.13inch e-Paper HAT (V4)
        "epd2in13_V3",  # 2.13inch e-Paper HAT (V3)
        "epd2in13",  # 2.13inch e-Paper HAT
        "epd2in9",  # 2.9inch e-Paper HAT
        "epd2in7",  # 2.7inch e-Paper HAT
        "epd4in2",  # 4.2inch e-Paper HAT
        "epd7in5",  # 7.5inch e-Paper HAT
    ]

    for model in models:
        try:
            print(f"  Trying {model}...", end=" ")
            module = __import__(f"waveshare_epd.{model}", fromlist=[model])
            epd_class = module.EPD

            # Try to initialize
            epd = epd_class()
            epd.init()

            # If we got here, this is the right model
            print("✓ DETECTED!")
            return epd, model
        except Exception as e:
            print(f"✗ ({type(e).__name__})")
            continue

    print("\n❌ Could not detect display model!")
    print("   Make sure the display is properly connected.")
    return None, None


def test_display(epd: object, model: str) -> bool:
    """Test the display by drawing a simple pattern."""
    print("\n" + "=" * 50)
    print(f"Testing display: {model}")
    print("=" * 50)

    try:
        from PIL import Image, ImageDraw, ImageFont

        print("  Creating test image...")

        # Create blank image
        width = epd.height  # Note: height/width are swapped for rotation
        height = epd.width
        image = Image.new("1", (width, height), 255)  # 1-bit, white background
        draw = ImageDraw.Draw(image)

        # Draw test pattern
        print("  Drawing test pattern...")

        # Border
        draw.rectangle([(0, 0), (width - 1, height - 1)], outline=0)

        # Text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except OSError:
            font = ImageFont.load_default()

        text_lines = [
            "BirdNET-Pi",
            "ePaper HAT Test",
            f"Model: {model}",
            f"Size: {width}x{height}",
        ]

        y_offset = 20
        for line in text_lines:
            draw.text((10, y_offset), line, font=font, fill=0)
            y_offset += 25

        # Diagonal lines
        draw.line([(0, 0), (width - 1, height - 1)], fill=0, width=2)
        draw.line([(0, height - 1), (width - 1, 0)], fill=0, width=2)

        print("  Displaying image...")
        epd.display(epd.getbuffer(image))

        print("  Waiting 5 seconds...")
        time.sleep(5)

        print("  Clearing display...")
        epd.init()
        epd.Clear()

        print("  Putting display to sleep...")
        epd.sleep()

        print("\n✓ Display test successful!")
        print("  If you saw the test pattern on the display, it's working correctly.")
        return True

    except Exception as e:
        print(f"\n❌ Display test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main() -> int:
    """Run all tests."""
    print("\n" + "=" * 50)
    print("Waveshare e-Paper HAT Test")
    print("=" * 50)
    print()

    # Check SPI
    if not check_spi_devices():
        print("\n" + "=" * 50)
        print("RESULT: SPI not available")
        print("=" * 50)
        return 1

    # Check Python module
    if not check_waveshare_module():
        print("\n" + "=" * 50)
        print("RESULT: waveshare_epd module not installed")
        print("=" * 50)
        return 1

    # Detect and test display
    epd, model = detect_display_model()
    if not epd:
        print("\n" + "=" * 50)
        print("RESULT: Could not detect display")
        print("=" * 50)
        return 1

    # Test the display
    success = test_display(epd, model)

    print("\n" + "=" * 50)
    if success:
        print("RESULT: ✓ All tests passed!")
        print("Your ePaper HAT is working correctly.")
    else:
        print("RESULT: ✗ Display test failed")
    print("=" * 50)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
