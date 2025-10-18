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
BRANCH="${BIRDNET_BRANCH:-feature/sbc-installer}"
INSTALL_DIR="${BIRDNET_INSTALL_DIR:-$HOME/BirdNET-Pi}"

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    echo "This script should not be run as root. Please run as a non-root user with sudo privileges."
    exit 1
fi

echo "========================================"
echo "BirdNET-Pi SBC Installer"
echo "========================================"
echo "Repository: $REPO_URL"
echo "Branch: $BRANCH"
echo "Install directory: $INSTALL_DIR"
echo ""

# Bootstrap the environment
echo "Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y git python3.11 python3.11-venv python3-pip whiptail

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Repository already exists at $INSTALL_DIR"
    echo "Pulling latest changes..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "Cloning repository..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Execute the main setup script
echo ""
echo "Starting installation..."
python3.11 "$INSTALL_DIR/install/setup_app.py"
