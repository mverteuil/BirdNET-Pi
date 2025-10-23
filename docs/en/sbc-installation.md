# SBC Installation Guide

This guide covers installing BirdNET-Pi on single-board computers (SBCs) like Raspberry Pi.

## Choosing Your Installation Method

**Attended Installation (Recommended)** - Use this method if:
- This is your first time installing BirdNET-Pi
- You want the simplest, most user-friendly experience
- You have access to a monitor and keyboard for initial setup
- You're comfortable using a web-based tool

**Unattended Installation (Advanced)** - Use this method if:
- You need completely headless installation (no monitor/keyboard)
- You're setting up multiple devices
- You want to pre-configure everything before first boot
- You're comfortable with command-line tools

---

## Attended Installation (Recommended)

The attended installation uses the official Raspberry Pi Imager to flash your SD card, then runs an interactive installer on first boot.

### Prerequisites

- Raspberry Pi 4B, 400, or 3B+ (or compatible SBC)
- MicroSD card (32GB or larger recommended)
- Computer with SD card reader
- Internet connection

### Step 1: Download Raspberry Pi Imager

Download the official Raspberry Pi Imager for your operating system:

- **Windows**: [Download for Windows](https://downloads.raspberrypi.org/imager/imager_latest.exe)
- **macOS**: [Download for macOS](https://downloads.raspberrypi.org/imager/imager_latest.dmg)
- **Ubuntu/Debian**:
  ```bash
  sudo apt install rpi-imager
  ```

Or visit the [official Raspberry Pi Imager page](https://www.raspberrypi.com/software/).

### Step 2: Flash Raspberry Pi OS

1. **Launch Raspberry Pi Imager**
2. **Choose Device**: Select your Raspberry Pi model
3. **Choose OS**:
   - Select "Raspberry Pi OS (other)"
   - Choose "Raspberry Pi OS Lite (64-bit)" (headless server, recommended)
   - Or "Raspberry Pi OS (64-bit)" if you want a desktop environment
4. **Choose Storage**: Select your SD card
5. **Configure Settings** (click the gear icon or "EDIT SETTINGS"):
   - Set hostname (e.g., `birdnetpi.local`)
   - Enable SSH (required)
   - Set username and password
   - Configure WiFi (if using wireless)
   - Set locale settings
6. **Write**: Click "Write" to flash the SD card

### Step 3: First Boot

1. Insert the SD card into your Raspberry Pi
2. Connect power (and optionally: ethernet, monitor, keyboard)
3. Wait for the Pi to boot (first boot takes longer)
4. Connect via SSH:
   ```bash
   ssh username@birdnetpi.local
   ```

### Step 4: Run the Installer

Once connected via SSH, run the one-line installer:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/mverteuil/BirdNET-Pi/main/install/install.sh)
```

The installer will:
- Install all required system dependencies
- Download BirdNET-Pi from GitHub
- Set up the Python environment
- Run an interactive configuration wizard
- Configure systemd services
- Start BirdNET-Pi daemons

### Step 5: Access the Web Interface

Once installation completes, access the web interface at:

```
http://birdnetpi.local:8000
```

Or use your device's IP address:

```
http://192.168.1.XXX:8000
```

---

## Unattended Installation (Advanced)

The unattended installation allows you to pre-configure everything and have BirdNET-Pi install automatically on first boot without any user interaction.

### Prerequisites

- Python 3.11+ (on your computer, for the flasher tool)
- `uv` (Python package manager) - [Installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
- MicroSD card (32GB or larger recommended)
- SD card reader

### Step 1: Clone the Repository

Clone the BirdNET-Pi repository to get the flasher tool:

```bash
git clone https://github.com/mverteuil/BirdNET-Pi.git
cd BirdNET-Pi
```

### Step 2: Run the SD Card Flasher

The flasher tool will:
- Download Raspberry Pi OS
- Flash it to your SD card
- Configure WiFi, SSH, and system settings
- Install BirdNET-Pi installer script
- Optionally save your configuration for future use

Run the flasher:

```bash
uv run install/flash_sdcard.py
```

The interactive wizard will prompt you for:
- SD card selection
- WiFi credentials
- SSH configuration
- Device hostname
- BirdNET-Pi location (latitude/longitude)
- Language preference
- Auto-install option (enable for completely unattended setup)

#### Saving Configuration for Multiple SD Cards

If you're setting up multiple BirdNET-Pi devices, use the `--save-config` flag to save your configuration:

```bash
uv run install/flash_sdcard.py --save-config
```

The configuration will be saved to `~/.config/birdnetpi/flash_config.json`.

On subsequent runs, the flasher will:
- Ask if you want to reuse the saved configuration
- Let you modify specific settings (like hostname or location)
- Flash multiple cards quickly with consistent settings

This is especially useful for:
- Installing BirdNET-Pi at multiple locations
- Creating backup devices
- Setting up a network of monitoring stations

### Step 3: Boot and Auto-Install

**If you enabled auto-install during flashing:**

1. Insert the SD card into your Raspberry Pi
2. Connect power and network
3. Wait 10-20 minutes for automatic installation
4. Access the web interface at `http://[hostname].local:8000`

**If you disabled auto-install:**

1. Insert the SD card into your Raspberry Pi
2. Connect power and network
3. SSH into the device:
   ```bash
   ssh username@hostname.local
   ```
4. Run the installer manually:
   ```bash
   sudo /boot/firmware/install.sh
   ```

The installer will run non-interactively using the pre-configured settings from the flash process.

### Step 4: Access the Web Interface

Once installation completes, access the web interface at:

```
http://[hostname].local:8000
```

Or use your device's IP address:

```
http://192.168.1.XXX:8000
```

---

## Supported Hardware

BirdNET-Pi is designed for flexibility and runs on various single-board computers:

- **Raspberry Pi 4B** (Recommended - best performance)
- **Raspberry Pi 400** (Desktop form factor)
- **Raspberry Pi 3B+** (Minimum recommended)
- **Libre Computer "Le Potato"**
- **Libre Computer "Renegade"**
- Other armv7l/aarch64 SBCs with Debian-based OS

### Hardware Recommendations

- **RAM**: 2GB minimum, 4GB+ recommended
- **Storage**: 32GB SD card minimum, 64GB+ for extended recording
- **Microphone**: USB microphone or USB sound card with external mic
- **Network**: Ethernet recommended for stability, WiFi supported
- **Power**: Official Raspberry Pi power supply (5V 3A for Pi 4)

---

## Distributed Setups

Thanks to the modular architecture, you can run BirdNET-Pi services on separate machines:

- **Audio capture** on one device (at the monitoring location)
- **Analysis** on another device (with more processing power)
- **Database** on a third device (centralized storage)

This advanced configuration requires manual setup and is not covered by the automatic installer. See the developer documentation for details.

---

## Troubleshooting

### SSH Connection Issues

If you can't connect via SSH:
- Verify SSH was enabled in Raspberry Pi Imager settings
- Check your network connection (try `ping hostname.local`)
- Try using IP address instead of hostname
- Wait longer - first boot can take 2-3 minutes

### Installer Fails

If the installer encounters errors:
- Check internet connectivity: `ping google.com`
- Verify you have enough disk space: `df -h`
- Check system logs: `journalctl -xe`
- Try running installer again (it's designed to be re-runnable)

### Can't Access Web Interface

If you can't access the web interface:
- Verify services are running: `systemctl status birdnetpi-*`
- Check firewall settings
- Try accessing via IP address instead of hostname
- Check logs: `journalctl -u birdnetpi-web -n 50`

### Audio Device Not Detected

If your microphone isn't detected:
- List audio devices: `arecord -l`
- Check USB connections
- Verify device drivers are loaded: `lsusb`
- See audio configuration guide (coming soon)

---

## Next Steps

After installation:

1. **[Configure Language Settings](./language-configuration.md)** - Set up multilingual species names
2. **Configure Audio** - Select microphone and adjust settings
3. **Set Location** - Configure precise GPS coordinates for accurate species detection
4. **Review Settings** - Customize analysis parameters, recording schedule, and notifications
5. **Add Notifications** - Set up alerts via MQTT, webhooks, or other services

---

## Getting Help

- **Documentation**: Browse the [user documentation](./index.md)
- **Issues**: Report problems on [GitHub Issues](https://github.com/mverteuil/BirdNET-Pi/issues)
- **Community**: Join discussions on GitHub Discussions (coming soon)

---

**Note**: This installation guide covers SBC installations. For Docker-based installation, see the [Docker Installation Guide](./docker-installation.md).
