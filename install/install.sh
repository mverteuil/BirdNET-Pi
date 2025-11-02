#!/usr/bin/env bash
# BirdNET-Pi SBC Installer Bootstrap Script
#
# One-liner installation (recommended):
#   bash <(curl -fsSL https://raw.githubusercontent.com/mverteuil/BirdNET-Pi/feature/sbc-installer/install/install.sh)
#
# Or download first:
#   curl -fsSL <url> -o install.sh && bash install.sh
#
# Test ePaper HAT only:
#   bash install.sh --test-epaper
set -e

# Configuration
REPO_URL="${BIRDNETPI_REPO_URL:-https://github.com/mverteuil/BirdNET-Pi.git}"
BRANCH="${BIRDNETPI_BRANCH:-main}"
INSTALL_DIR="/opt/birdnetpi"

# Parse command line arguments
TEST_EPAPER=false
if [ "$1" = "--test-epaper" ]; then
    TEST_EPAPER=true
fi

# Check if running as root - convert sudo to su
if [ "$(id -u)" -eq 0 ]; then
    echo "Running as root - converting sudo commands to su"
    sudo() {
        local user=""
        local env_vars=()
        local cmd=()

        while [[ $# -gt 0 ]]; do
            case "$1" in
                -u|--user)
                    user="$2"
                    shift 2
                    ;;
                -g|--group)
                    # Skip group flag (su doesn't support it the same way)
                    shift 2
                    ;;
                -*)
                    # Skip other sudo flags
                    shift
                    ;;
                *=*)
                    # Environment variable assignment
                    env_vars+=("$1")
                    shift
                    ;;
                *)
                    # Rest are command arguments
                    cmd=("$@")
                    break
                    ;;
            esac
        done

        if [ -n "$user" ]; then
            if [ ${#env_vars[@]} -gt 0 ]; then
                su - "$user" -c "env ${env_vars[*]} ${cmd[*]}"
            else
                su - "$user" -c "${cmd[*]}"
            fi
        else
            # No user specified, run as root with env vars if present
            if [ ${#env_vars[@]} -gt 0 ]; then
                env "${env_vars[@]}" "${cmd[@]}"
            else
                "${cmd[@]}"
            fi
        fi
    }
    export -f sudo
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
sudo apt-get install -y git python3.11 python3.11-venv python3-pip build-essential python3.11-dev

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
sudo usermod -aG audio,video,dialout,spi,gpio birdnetpi
sudo chown birdnetpi:birdnetpi "$INSTALL_DIR"

# Clone repository directly to installation directory as birdnetpi user
echo "Cloning repository..."
sudo -u birdnetpi git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

# Install uv package manager system-wide to /opt/uv
echo "Installing uv package manager..."
sudo mkdir -p /opt/uv
sudo curl -LsSf https://astral.sh/uv/install.sh | sudo INSTALLER_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/opt/uv sh

# Detect Waveshare e-paper HAT via SPI devices (or force for test mode)
EPAPER_EXTRAS=""
if [ "$TEST_EPAPER" = true ]; then
    echo "Test mode: forcing ePaper HAT extras installation"
    EPAPER_EXTRAS="--extra epaper"
elif ls /dev/spidev* &>/dev/null; then
    echo "Waveshare e-paper HAT detected (SPI devices found)"
    EPAPER_EXTRAS="--extra epaper"
else
    echo "No e-paper HAT detected, skipping epaper extras"
fi

# Wait for network and DNS to be ready (git uses different DNS than ping)
echo "Checking network connectivity..."
MAX_NETWORK_WAIT=30
NETWORK_WAIT=0
while [ $NETWORK_WAIT -lt $MAX_NETWORK_WAIT ]; do
    # Test with both ping and git ls-remote to ensure DNS works for both
    if ping -c 1 -W 2 github.com >/dev/null 2>&1 && \
       git ls-remote --exit-code https://github.com/waveshareteam/e-Paper.git HEAD >/dev/null 2>&1; then
        echo "Network and DNS ready (verified with git)"
        break
    fi
    NETWORK_WAIT=$((NETWORK_WAIT + 1))
    if [ $NETWORK_WAIT -lt $MAX_NETWORK_WAIT ]; then
        echo "Waiting for network and DNS... ($NETWORK_WAIT/$MAX_NETWORK_WAIT)"
        sleep 2
    else
        echo "WARNING: Network check timed out, proceeding anyway..."
    fi
done

# Give DNS resolver a moment to stabilize
sleep 2

# If Waveshare library was downloaded to boot partition, copy to writable location
WAVESHARE_BOOT_PATH="/boot/firmware/waveshare-epd"
WAVESHARE_LIB_PATH="/opt/birdnetpi/waveshare-epd"
if [ -d "$WAVESHARE_BOOT_PATH" ] && [ -n "$EPAPER_EXTRAS" ]; then
    echo "Using pre-downloaded Waveshare library from boot partition..."

    # Copy from boot partition (FAT32, root-owned) to writable location
    # This is needed because uv needs write access to build the package
    sudo cp -r "$WAVESHARE_BOOT_PATH" "$WAVESHARE_LIB_PATH"
    sudo chown -R birdnetpi:birdnetpi "$WAVESHARE_LIB_PATH"

    cd "$INSTALL_DIR"

    # Patch pyproject.toml to use the copied local path instead of git URL
    sudo -u birdnetpi sed -i 's|waveshare-epd = {git = "https://github.com/waveshareteam/e-Paper.git", subdirectory = "RaspberryPi_JetsonNano/python"}|waveshare-epd = {path = "/opt/birdnetpi/waveshare-epd"}|' pyproject.toml

    # Regenerate lockfile since we changed the source
    echo "Regenerating lockfile for local Waveshare library..."
    sudo -u birdnetpi UV_HTTP_TIMEOUT=300 /opt/uv/uv lock --quiet

    echo "✓ Configured to use local Waveshare library"
fi

# Install Python dependencies with retry mechanism (for network issues)
echo "Installing Python dependencies..."
cd "$INSTALL_DIR"
UV_CMD="sudo -u birdnetpi UV_HTTP_TIMEOUT=300 UV_EXTRA_INDEX_URL=https://www.piwheels.org/simple /opt/uv/uv sync --locked --no-dev --quiet"
if [ -n "$EPAPER_EXTRAS" ]; then
    UV_CMD="$UV_CMD $EPAPER_EXTRAS"
fi

MAX_RETRIES=3
RETRY_COUNT=0
RETRY_DELAY=5

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if eval "$UV_CMD"; then
        echo "Python dependencies installed successfully"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Failed to install dependencies (attempt $RETRY_COUNT/$MAX_RETRIES)"
            echo "Waiting $RETRY_DELAY seconds before retry..."
            sleep $RETRY_DELAY
            # Increase delay for next retry (exponential backoff)
            RETRY_DELAY=$((RETRY_DELAY * 2))
            echo "Retrying dependency installation (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)..."
        else
            echo "ERROR: Failed to install Python dependencies after $MAX_RETRIES attempts"
            echo "This usually indicates a network issue. Please check your internet connection and try again."
            exit 1
        fi
    fi
done

# If test mode, run ePaper test and exit
if [ "$TEST_EPAPER" = true ]; then
    echo ""
    echo "========================================"
    echo "ePaper HAT Test Mode"
    echo "========================================"
    echo ""
    "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/install/test_epaper.py"
    exit $?
fi

# Execute the main setup script using the venv directly
# We use the venv's python instead of uv run to avoid permission issues
# (uv sync ran as birdnetpi, but setup_app.py needs sudo for system operations)
echo ""
echo "Starting installation..."
"$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/install/setup_app.py"
