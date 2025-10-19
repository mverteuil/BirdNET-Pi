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

# Bootstrap the environment
echo "Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y git python3.11 python3.11-venv python3-pip

# Create birdnetpi user early (needed for ownership)
echo "Creating birdnetpi user..."
sudo useradd -m -s /bin/bash birdnetpi 2>/dev/null || true
sudo usermod -aG audio,video,dialout birdnetpi

# Create installation directory with proper ownership
if [ -d "$INSTALL_DIR" ]; then
    echo "Cleaning up existing installation directory..."
    sudo rm -rf "$INSTALL_DIR"
fi

echo "Creating installation directory..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown birdnetpi:birdnetpi "$INSTALL_DIR"

# Clone repository directly to installation directory as birdnetpi user
echo "Cloning repository..."
sudo -u birdnetpi git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

# Execute the main setup script
echo ""
echo "Starting installation..."
cd "$INSTALL_DIR"
python3.11 "$INSTALL_DIR/install/setup_app.py"
