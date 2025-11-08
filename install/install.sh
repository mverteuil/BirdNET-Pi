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
# NOTE: These defaults are substituted by flash_sdcard.py at flash time
# based on the configured repo URL and branch in the flasher wizard
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
echo "Checking SPI interface..."

# Check if SPI devices already exist
if ls /dev/spidev* &>/dev/null; then
    echo "SPI already enabled (devices found)"
else
    SPI_ENABLED=false

    # Raspberry Pi OS: /boot/firmware/config.txt
    BOOT_CONFIG="/boot/firmware/config.txt"
    if [ -f "$BOOT_CONFIG" ]; then
        echo "Detected Raspberry Pi OS, checking $BOOT_CONFIG..."
        if grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
            SPI_ENABLED=true
        else
            echo "Enabling SPI in $BOOT_CONFIG..."
            # Uncomment if commented, or add if missing
            if grep -q "^#dtparam=spi=on" "$BOOT_CONFIG"; then
                sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$BOOT_CONFIG"
            else
                echo "dtparam=spi=on" | sudo tee -a "$BOOT_CONFIG" > /dev/null
            fi
            SPI_ENABLED=true
        fi
    fi

    # DietPi/Armbian on Orange Pi: /boot/armbianEnv.txt or /boot/dietpiEnv.txt
    for ARMBIAN_CONFIG in "/boot/armbianEnv.txt" "/boot/dietpiEnv.txt"; do
        if [ -f "$ARMBIAN_CONFIG" ]; then
            echo "Detected Armbian/DietPi, checking $ARMBIAN_CONFIG..."

            # Check for any SPI overlay (platform-specific like rk3588-spi* or generic spi-spidev)
            if grep -q "^overlays=.*spi" "$ARMBIAN_CONFIG"; then
                echo "SPI overlay found in $ARMBIAN_CONFIG"

                # Check if overlay has chip prefix (e.g., rk3588-) which needs to be removed
                # DietPi/Armbian automatically prepend the prefix from overlay_prefix config
                if grep -q "^overlays=.*rk3588-spi" "$ARMBIAN_CONFIG"; then
                    echo "Fixing RK3588 SPI overlay format (removing chip prefix)..."
                    # Replace rk3588-spi4-m0-cs1-spidev with spi4-m2-cs0-spidev (M2-CS0 is the working variant)
                    sudo sed -i 's/rk3588-spi4-[^ ]*/spi4-m2-cs0-spidev/' "$ARMBIAN_CONFIG"
                    SPI_ENABLED=true
                fi

                # Verify param_spidev_spi_bus parameter exists
                if ! grep -q "^param_spidev_spi_bus=" "$ARMBIAN_CONFIG"; then
                    echo "Adding param_spidev_spi_bus=0 to $ARMBIAN_CONFIG..."
                    echo "param_spidev_spi_bus=0" | sudo tee -a "$ARMBIAN_CONFIG" > /dev/null
                    SPI_ENABLED=true
                fi

                # Verify param_spidev_max_freq parameter exists (required for RK3588)
                if ! grep -q "^param_spidev_max_freq=" "$ARMBIAN_CONFIG"; then
                    echo "Adding param_spidev_max_freq=100000000 to $ARMBIAN_CONFIG..."
                    echo "param_spidev_max_freq=100000000" | sudo tee -a "$ARMBIAN_CONFIG" > /dev/null
                    SPI_ENABLED=true
                fi

                if [ "$SPI_ENABLED" != true ]; then
                    echo "SPI already configured correctly in $ARMBIAN_CONFIG"
                fi
            else
                echo "Enabling SPI in $ARMBIAN_CONFIG..."
                # Check if overlays line exists
                if grep -q "^overlays=" "$ARMBIAN_CONFIG"; then
                    # Add spi-spidev to existing overlays
                    sudo sed -i 's/^overlays=\(.*\)/overlays=\1 spi-spidev/' "$ARMBIAN_CONFIG"
                else
                    # Create new overlays line
                    echo "overlays=spi-spidev" | sudo tee -a "$ARMBIAN_CONFIG" > /dev/null
                fi

                # Add param_spidev_spi_bus parameter
                echo "param_spidev_spi_bus=0" | sudo tee -a "$ARMBIAN_CONFIG" > /dev/null

                SPI_ENABLED=true
            fi
            break
        fi
    done

    if [ "$SPI_ENABLED" = true ]; then
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
    else
        echo "WARNING: Could not detect system type to enable SPI"
        echo "SPI may need to be enabled manually for e-paper HAT support"
    fi
fi

# Bootstrap the environment
echo "Installing prerequisites..."
sudo apt-get update
# Minimal build dependencies (no perl, make, or other build-essential bloat)
sudo apt-get install -y git python3.11 python3.11-venv python3-pip gcc libc6-dev python3.11-dev libportaudio2 libsndfile1

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

# Create spi and gpio groups if they don't exist (needed for DietPi/Orange Pi)
getent group spi >/dev/null || sudo groupadd spi
getent group gpio >/dev/null || sudo groupadd gpio

sudo usermod -aG audio,video,dialout,spi,gpio birdnetpi
sudo chown birdnetpi:birdnetpi "$INSTALL_DIR"

# Grant birdnetpi user limited sudo access for systemctl commands
# This allows the web UI to query and control services without root access
echo "Configuring sudoers for service management..."
cat <<'EOF' | sudo tee /etc/sudoers.d/birdnetpi-systemctl > /dev/null
# Allow birdnetpi user to query and control birdnetpi services
# This is needed for the web UI to show service status
birdnetpi ALL=(root) NOPASSWD: /usr/bin/systemctl show birdnetpi-* *, \
                              /usr/bin/systemctl is-active birdnetpi-*, \
                              /usr/bin/systemctl start birdnetpi-*, \
                              /usr/bin/systemctl stop birdnetpi-*, \
                              /usr/bin/systemctl restart birdnetpi-*, \
                              /usr/bin/systemctl enable birdnetpi-*, \
                              /usr/bin/systemctl disable birdnetpi-*, \
                              /usr/bin/systemctl daemon-reload, \
                              /usr/bin/systemctl show caddy *, \
                              /usr/bin/systemctl is-active caddy, \
                              /usr/bin/systemctl start caddy, \
                              /usr/bin/systemctl stop caddy, \
                              /usr/bin/systemctl restart caddy, \
                              /usr/bin/systemctl show redis *, \
                              /usr/bin/systemctl is-active redis, \
                              /usr/bin/systemctl start redis, \
                              /usr/bin/systemctl restart redis, \
                              /usr/bin/systemctl reboot
EOF
sudo chmod 0440 /etc/sudoers.d/birdnetpi-systemctl

# Clone repository directly to installation directory as birdnetpi user
echo "Cloning repository..."
sudo -u birdnetpi git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

# Copy config file from /root to installation directory (if it exists)
# This makes it accessible to the birdnetpi user
if [ -f /root/birdnetpi_config.json ]; then
    echo "Copying configuration file..."
    sudo cp /root/birdnetpi_config.json "$INSTALL_DIR/birdnetpi_config.json"
    sudo chown birdnetpi:birdnetpi "$INSTALL_DIR/birdnetpi_config.json"
fi

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

# Create cache directory for uv in tmpfs
# Using /tmp instead of /dev/shm as /dev/shm is often too small (512MB default)
# /tmp is larger and still avoids excessive SD card writes on most systems
UV_CACHE_DIR="/tmp/uv-cache"
sudo mkdir -p "$UV_CACHE_DIR"
sudo chown birdnetpi:birdnetpi "$UV_CACHE_DIR"

# If Waveshare library was downloaded to boot partition, extract/copy to writable location
# Check multiple possible locations as boot partition mount varies by system
WAVESHARE_TARBALL_LOCATIONS=(
    "/boot/firmware/waveshare-epd.tar.gz"
    "/boot/waveshare-epd.tar.gz"
    "/root/waveshare-epd.tar.gz"  # Fallback location from rootfs copy
)
WAVESHARE_DIR_LOCATIONS=(
    "/boot/firmware/waveshare-epd"
    "/boot/waveshare-epd"
    "/root/waveshare-epd"
)
WAVESHARE_LIB_PATH="/opt/birdnetpi/waveshare-epd"
WAVESHARE_FOUND=""

if [ -n "$EPAPER_EXTRAS" ]; then
    # Try to find tarball first (preferred)
    for tarball_path in "${WAVESHARE_TARBALL_LOCATIONS[@]}"; do
        if [ -f "$tarball_path" ]; then
            echo "Extracting pre-downloaded Waveshare library from $tarball_path..."
            sudo mkdir -p /opt/birdnetpi
            sudo tar -xzf "$tarball_path" -C /opt/birdnetpi
            sudo chown -R birdnetpi:birdnetpi "$WAVESHARE_LIB_PATH"
            WAVESHARE_FOUND="yes"
            break
        fi
    done

    # Fall back to uncompressed directory (backward compatibility)
    if [ -z "$WAVESHARE_FOUND" ]; then
        for dir_path in "${WAVESHARE_DIR_LOCATIONS[@]}"; do
            if [ -d "$dir_path" ]; then
                echo "Copying pre-downloaded Waveshare library from $dir_path..."
                sudo cp -r "$dir_path" "$WAVESHARE_LIB_PATH"
                sudo chown -R birdnetpi:birdnetpi "$WAVESHARE_LIB_PATH"
                WAVESHARE_FOUND="yes"
                break
            fi
        done
    fi

    if [ -n "$WAVESHARE_FOUND" ]; then
        cd "$INSTALL_DIR"

        # Patch pyproject.toml to use the local path instead of git URL
        # Use a temp script to avoid quote escaping issues with su -c wrapper
        cat > /tmp/patch_pyproject.sh << 'SEDEOF'
#!/bin/sh
cd /opt/birdnetpi
sed -i 's|waveshare-epd = {git = "https://github.com/waveshareteam/e-Paper.git", subdirectory = "RaspberryPi_JetsonNano/python"}|waveshare-epd = {path = "/opt/birdnetpi/waveshare-epd"}|' pyproject.toml
SEDEOF
        chmod +x /tmp/patch_pyproject.sh
        sudo -u birdnetpi /tmp/patch_pyproject.sh
        rm -f /tmp/patch_pyproject.sh

        # Regenerate lockfile with the local path (respects the patched pyproject.toml)
        sudo -u birdnetpi UV_CACHE_DIR="$UV_CACHE_DIR" /opt/uv/uv lock

        # Patch Waveshare library to support Orange Pi (uses same GPIO pinout as Raspberry Pi)
        if [ -f "$WAVESHARE_LIB_PATH/lib/waveshare_epd/epdconfig.py" ]; then
            echo "Patching Waveshare library for Orange Pi support..."
            python3 "$INSTALL_DIR/install/patch_waveshare_orangepi.py" "$WAVESHARE_LIB_PATH/lib/waveshare_epd/epdconfig.py"
        fi

        echo "✓ Configured to use local Waveshare library"
    else
        echo "Note: Pre-downloaded Waveshare library not found, will download from GitHub"
    fi
fi

# Install Python dependencies with retry mechanism (for network issues)
echo "Installing Python dependencies..."
cd "$INSTALL_DIR"
UV_CMD="sudo -u birdnetpi UV_CACHE_DIR=$UV_CACHE_DIR UV_HTTP_TIMEOUT=300 UV_EXTRA_INDEX_URL=https://www.piwheels.org/simple /opt/uv/uv sync --locked --no-dev"
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

# Pass config values as environment variables if they were set
export BIRDNETPI_OS_KEY="${os_key:-}"
export BIRDNETPI_DEVICE_KEY="${device_key:-}"
export BIRDNETPI_DEVICE_NAME="${device_name:-}"
export BIRDNETPI_LATITUDE="${latitude:-}"
export BIRDNETPI_LONGITUDE="${longitude:-}"
export BIRDNETPI_TIMEZONE="${timezone:-}"
export BIRDNETPI_LANGUAGE="${language:-}"

"$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/install/setup_app.py"

# Clean up uv cache from tmpfs to free RAM
echo "Cleaning up temporary cache..."
sudo rm -rf /dev/shm/uv-cache
