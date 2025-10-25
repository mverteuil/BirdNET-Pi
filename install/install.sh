#!/usr/bin/env bash
# BirdNET-Pi SBC Installer Bootstrap Script
#
# One-liner installation (recommended):
#   bash <(curl -fsSL https://raw.githubusercontent.com/mverteuil/BirdNET-Pi/feature/sbc-installer/install/install.sh)
#
# Or download first:
#   curl -fsSL <url> -o install.sh && bash install.sh
set -e

# Configuration
REPO_URL="${BIRDNET_REPO_URL:-https://github.com/mverteuil/BirdNET-Pi.git}"
BRANCH="${BIRDNET_BRANCH:-main}"
INSTALL_DIR="/opt/birdnetpi"

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    echo "This script should not be run as root. Please run as a non-root user with sudo privileges."
    exit 1
fi

echo "========================================"
echo "BirdNET-Pi SBC Pre-installer"
echo "========================================"
echo "Repository: $REPO_URL"
echo "Branch: $BRANCH"
echo "Installation directory: $INSTALL_DIR"
echo ""
echo "Data will install to: /var/lib/birdnetpi"
echo ""

# Enable SPI interface early (required for e-paper HAT detection)
# Must reboot immediately for SPI devices to appear at /dev/spidev*
BOOT_CONFIG="/boot/firmware/config.txt"
if [ -f "$BOOT_CONFIG" ]; then
    echo "Checking SPI interface..."
    if grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
        echo "SPI already enabled"
    else
        echo "Enabling SPI interface..."
        # Uncomment if commented, or add if missing
        if grep -q "^#dtparam=spi=on" "$BOOT_CONFIG"; then
            sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$BOOT_CONFIG"
        else
            echo "dtparam=spi=on" | sudo tee -a "$BOOT_CONFIG" > /dev/null
        fi
        echo ""
        echo "========================================"
        echo "SPI interface enabled!"
        echo "System must reboot for changes to take effect."
        echo ""
        echo "After reboot, re-run this installer:"
        echo "  curl -fsSL <url> | bash"
        echo "or"
        echo "  bash install.sh"
        echo "========================================"
        echo ""
        read -r -p "Press Enter to reboot now, or Ctrl+C to cancel..."
        sudo reboot
        exit 0
    fi
fi

# Bootstrap the environment
echo "Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y git python3.11 python3.11-venv python3-pip

# Wait for DNS to settle after apt operations
sleep 2

# Create installation directory first (will become home directory)
if [ -d "$INSTALL_DIR" ]; then
    echo "Cleaning up existing installation directory..."
    sudo rm -rf "$INSTALL_DIR"
fi

echo "Creating installation directory..."
sudo mkdir -p "$INSTALL_DIR"

# Create or update birdnetpi user with /opt/birdnetpi as home directory
echo "Setting up birdnetpi user..."
if id "birdnetpi" &>/dev/null; then
    # User exists - update home directory (unless currently logged in as birdnetpi)
    if [ "$USER" = "birdnetpi" ]; then
        echo "Note: Cannot modify birdnetpi user while logged in as that user"
        echo "      Home directory will be set to $INSTALL_DIR on next login"
    else
        sudo usermod -d "$INSTALL_DIR" birdnetpi
    fi
else
    # User doesn't exist - create with /opt/birdnetpi as home (no -m since dir exists)
    sudo useradd -d "$INSTALL_DIR" -s /bin/bash birdnetpi
fi
sudo usermod -aG audio,video,dialout birdnetpi
sudo chown birdnetpi:birdnetpi "$INSTALL_DIR"

# Clone repository directly to installation directory as birdnetpi user
echo "Cloning repository..."
sudo -u birdnetpi git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

# Install uv package manager system-wide to /opt/uv
echo "Installing uv package manager..."
sudo mkdir -p /opt/uv
sudo curl -LsSf https://astral.sh/uv/install.sh | sudo INSTALLER_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/opt/uv sh

# Detect Waveshare e-paper HAT via SPI devices
EPAPER_EXTRAS=""
if ls /dev/spidev* &>/dev/null; then
    echo "Waveshare e-paper HAT detected (SPI devices found)"
    EPAPER_EXTRAS="--extra epaper"
else
    echo "No e-paper HAT detected, skipping epaper extras"
fi

# Install Python dependencies (makes Jinja2 available for setup_app.py)
echo "Installing Python dependencies..."
cd "$INSTALL_DIR"
UV_CMD="sudo -u birdnetpi /opt/uv/uv sync --locked --no-dev --quiet"
if [ -n "$EPAPER_EXTRAS" ]; then
    UV_CMD="$UV_CMD $EPAPER_EXTRAS"
fi
eval "$UV_CMD"

# Execute the main setup script with uv run (dependencies now available)
echo ""
echo "Starting installation..."
/opt/uv/uv run python "$INSTALL_DIR/install/setup_app.py"
