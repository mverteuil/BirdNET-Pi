# E-Paper Display Support

BirdNET-Pi supports Waveshare e-paper HAT displays on Raspberry Pi and other single-board computers (SBCs). The display provides a low-power, always-on status screen showing system health and recent bird detections.

## Supported Devices

BirdNET-Pi supports three Waveshare e-paper HAT models with 250×122 pixel resolution. All models share the same physical dimensions and SPI interface, differing only in color support.

### Waveshare 2.13" e-Paper HAT (B) V4 (Recommended)

**Configuration:** `2in13b_V4` (default)
**Resolution:** 250×122 pixels
**Colors:** 3-color (Black/White/Red)
**Interface:** SPI
**Compatible Platforms:** Raspberry Pi (all models), Jetson Nano

![Waveshare 2.13" HAT (B) V4](https://www.waveshare.com/img/devkit/accBoard/2.13inch-e-Paper-HAT-B/2.13inch-e-Paper-HAT-B-1.jpg)

**Features:**
- **Red color highlighting** for new bird detection alerts
- Ultra-low power consumption (no power when not refreshing)
- Wide viewing angle (nearly 180°)
- Retains image without power
- No backlight required
- Sunlight readable

**Specifications:**
- Display size: 2.13 inches
- Outline dimensions: 65mm × 30.2mm
- Pixel resolution: 250×122
- Display colors: Black, White, Red
- Interface: SPI
- Refresh time: ~15 seconds (full refresh)
- Operating voltage: 3.3V
- Limited refresh cycles (~100,000 refreshes)

### Waveshare 2.13" e-Paper HAT (B) V3

**Configuration:** `2in13b_V3`
**Resolution:** 250×122 pixels
**Colors:** 3-color (Black/White/Red)
**Interface:** SPI
**Compatible Platforms:** Raspberry Pi (all models), Jetson Nano

Previous generation 3-color display. Identical specifications to V4, but uses older driver chip. Fully supported with red color highlighting for detection alerts.

### Waveshare 2.13" e-Paper HAT V4

**Configuration:** `2in13_V4`
**Resolution:** 250×122 pixels
**Colors:** 2-color (Black/White)
**Interface:** SPI
**Compatible Platforms:** Raspberry Pi (all models), Jetson Nano

2-color variant without red channel. Detection alerts use black border highlighting instead of red color.

## What the Display Shows

The e-paper display provides at-a-glance monitoring of your BirdNET-Pi system:

### System Status
- **Site Name**: Your configured site name (up to 20 characters)
- **Current Time**: System time in HH:MM format
- **CPU Usage**: Percentage of CPU utilization
- **Memory Usage**: Percentage of RAM used
- **Disk Usage**: Percentage of storage used

### Health Indicators
- **System Health**: ✓ (ready) or ✗ (unhealthy)
- **Database Status**: ✓ (connected) or ✗ (disconnected)

### Detection Information
- **Latest Bird Detection**: Common name of most recently detected bird
- **Confidence Level**: Detection confidence as percentage
- **Detection Time**: Timestamp of detection (HH:MM:SS)
- **Visual Alert**: New detections highlighted for 3 refresh cycles (~90 seconds)
  - **3-color displays (2in13b_V3/V4)**: Red color highlighting for detection name and header
  - **2-color displays (2in13_V4)**: Black border highlighting around detection area

## Hardware Installation

### Physical Connection

1. **Power off** your Raspberry Pi completely
2. Locate the 40-pin GPIO header on your Raspberry Pi
3. Align the e-paper HAT with the GPIO header (pin 1 to pin 1)
4. Gently press the HAT onto the GPIO pins until fully seated
5. The HAT should sit flat against the Raspberry Pi

**Important:** Never connect or disconnect the HAT while the Pi is powered on.

### GPIO Pin Usage

The Waveshare 2.13" V4 uses the following GPIO pins:

| Function | BCM Pin | Physical Pin |
|----------|---------|--------------|
| VCC      | 3.3V    | 1 or 17     |
| GND      | Ground  | 6, 9, 14, 20, 25, 30, 34, 39 |
| DIN (MOSI) | GPIO 10 | 19 |
| CLK      | GPIO 11 | 23          |
| CS       | GPIO 8  | 24          |
| DC       | GPIO 25 | 22          |
| RST      | GPIO 17 | 11          |
| BUSY     | GPIO 24 | 18          |

These pins are automatically configured when you install the e-paper dependencies.

## Software Installation

### Prerequisites

- Raspberry Pi OS (32-bit or 64-bit)
- Python 3.11 (installed with BirdNET-Pi)
- SPI interface enabled

### Enable SPI Interface

The Waveshare HAT requires SPI to be enabled on your Raspberry Pi:

```bash
# Option 1: Using raspi-config
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# Option 2: Using command line
sudo raspi-config nonint do_spi 0

# Option 3: Manual edit
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

Verify SPI is enabled:
```bash
lsmod | grep spi_
# Should show: spi_bcm2835
```

### Install E-Paper Dependencies

On your Raspberry Pi with BirdNET-Pi installed:

```bash
# Navigate to BirdNET-Pi directory
cd /opt/birdnetpi

# Install optional e-paper dependencies
source .venv/bin/activate
uv pip install -e .[epaper]
```

This installs:
- `waveshare-epd`: Official Waveshare e-paper driver library
- `RPi.GPIO`: GPIO control library for Raspberry Pi
- `spidev`: Python SPI library

### Enable the Display Service

The e-paper display runs as a systemd service:

```bash
# Enable and start the service
sudo systemctl enable birdnetpi-epaper-display.service
sudo systemctl start birdnetpi-epaper-display.service

# Check service status
sudo systemctl status birdnetpi-epaper-display.service

# View logs
sudo journalctl -u birdnetpi-epaper-display.service -f
```

## Configuration

Configure the e-paper display through the BirdNET-Pi web interface or by editing the configuration file.

### Via Web Interface

1. Navigate to **Settings** in the BirdNET-Pi web UI
2. Scroll to **E-Paper Display** section
3. Configure the following options:

### Configuration Options

| Setting | Description | Default | Valid Values |
|---------|-------------|---------|--------------|
| `enable_epaper_display` | Enable/disable the display | `false` | `true`, `false` |
| `epaper_refresh_interval` | Seconds between display refreshes | `30` | `5` to `300` |
| `epaper_display_type` | Waveshare model identifier | `2in13b_V4` | `2in13_V4`, `2in13b_V3`, `2in13b_V4` |

### Configuration File

Edit `/var/lib/birdnetpi/config/birdnetpi.yaml`:

```yaml
# E-Paper Display Configuration
enable_epaper_display: true
epaper_refresh_interval: 30  # Refresh every 30 seconds (recommended)
epaper_display_type: "2in13b_V4"  # 3-color display with red highlighting
```

**Important Notes:**
- **Refresh Interval**: E-paper displays have limited refresh cycles (~100,000). Setting too frequent refreshes will shorten display lifespan. Recommended: 30-60 seconds for normal use.
- **Display Type**: Must match your physical hardware. Supported models: `2in13_V4` (2-color), `2in13b_V3` (3-color), `2in13b_V4` (3-color, recommended).

### Apply Configuration Changes

After modifying the configuration:

```bash
# Restart the e-paper service
sudo systemctl restart birdnetpi-epaper-display.service
```

## Testing Without Hardware

The e-paper display service includes a **simulation mode** for testing without physical hardware. When the Waveshare library is not available, the display output is saved to a PNG file.

### Run in Simulation Mode

```bash
# On any system (doesn't require Raspberry Pi)
cd /opt/birdnetpi
source .venv/bin/activate

# Install dependencies without e-paper hardware libraries
uv pip install -e .

# Run the daemon manually
epaper-display-daemon
```

The display output will be saved to:
```
# For all displays:
/var/lib/birdnetpi/display_output_black.png

# For 3-color displays (2in13b_V3, 2in13b_V4) additionally:
/var/lib/birdnetpi/display_output_red.png
```

You can view these files to see what would appear on the physical display. For 3-color displays, the red layer shows the colored elements that highlight new detections.

### Docker Testing

For development and testing, simulation mode runs automatically in Docker containers:

```bash
# Build and run
docker-compose up -d
```

**View the simulator output via web browser:**
- Black layer: `http://localhost:8000/display-simulator/display_output_black.png`
- Red layer (3-color displays): `http://localhost:8000/display-simulator/display_output_red.png`

**Or extract files via command line:**
```bash
# View simulated display output (black layer)
docker exec -it birdnet-pi cat /var/lib/birdnetpi/display_output_black.png > display_output_black.png

# For 3-color displays, also view the red layer
docker exec -it birdnet-pi cat /var/lib/birdnetpi/display_output_red.png > display_output_red.png
```

## Troubleshooting

### Display Not Updating

**Check service status:**
```bash
sudo systemctl status birdnetpi-epaper-display.service
```

**Check logs for errors:**
```bash
sudo journalctl -u birdnetpi-epaper-display.service -n 50
```

**Common issues:**
- SPI not enabled → Enable SPI in raspi-config
- Display not detected → Check physical connection
- Permission errors → Service should run as root

### "ImportError: No module named waveshare_epd"

The e-paper dependencies are not installed:
```bash
cd /opt/birdnetpi
source .venv/bin/activate
uv pip install -e .[epaper]
```

### Display Shows Partial/Corrupted Image

- **Cause**: Connection issue or interference
- **Solution**:
  1. Power off completely
  2. Reseat the HAT firmly
  3. Ensure no loose connections
  4. Check for GPIO conflicts with other HATs

### Display Not Clearing After Shutdown

The display retains the last image when powered off (this is normal e-paper behavior). To clear:

```bash
# Manually clear the display
sudo systemctl stop birdnetpi-epaper-display.service
# Display will clear on service stop
```

### High CPU Usage

E-paper refreshes are CPU-intensive. Increase the refresh interval:
```yaml
epaper_refresh_interval: 60  # Reduce to once per minute
```

### Display Lifespan Concerns

E-paper displays have limited refresh cycles:
- **Rated cycles**: ~100,000 full refreshes
- **Conservative refresh interval**: 60 seconds = ~1,000 refreshes/day
- **Estimated lifespan**: 100+ days of continuous use

Recommendations:
- Use 30-60 second refresh intervals
- Disable display when not needed
- Consider partial refresh modes (future enhancement)

## Advanced: Display Layout Customization

The display layout is defined in `src/birdnetpi/display/epaper.py`. Advanced users can modify:

- Font sizes and styles
- Information layout
- Color usage (black/red)
- Animation effects

**Warning**: Modifying the display service requires Python knowledge and may void support.

## Future Enhancements

Planned features for e-paper display support:

- [ ] Additional Waveshare models (larger displays)
- [ ] Partial refresh mode (longer display lifespan)
- [ ] Customizable display layouts via web UI
- [ ] Multiple display configurations
- [ ] Display rotation support
- [ ] Low-power sleep mode

## References

### Product Pages
- [Waveshare 2.13" HAT V4 (2-color)](https://www.waveshare.com/2.13inch-e-paper-hat.htm)
- [Waveshare 2.13" HAT (B) V4 (3-color)](https://www.waveshare.com/2.13inch-e-paper-hat-b.htm)
- [Waveshare 2.13" HAT (B) V3 (3-color)](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B))

### Documentation
- [Waveshare 2.13" Wiki (general)](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT)
- [Waveshare 2.13" (B) Wiki (3-color)](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_(B))
- [Official Python Examples](https://github.com/waveshareteam/e-Paper)
- [Raspberry Pi SPI Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#serial-peripheral-interface-spi)

## Support

If you encounter issues with e-paper display support:

1. Check the troubleshooting section above
2. Review service logs: `sudo journalctl -u birdnetpi-epaper-display.service`
3. Test in simulation mode to isolate hardware issues
4. Open an issue on [BirdNET-Pi GitHub](https://github.com/your-repo/BirdNET-Pi/issues) with logs

---

**Note**: E-paper displays are optional hardware. BirdNET-Pi functions fully without them. The display is primarily useful for:
- Remote/outdoor installations
- Monitoring without web access
- Low-power status indicators
- Educational/demonstration purposes
