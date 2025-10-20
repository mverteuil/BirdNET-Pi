#!/bin/bash
set -e

echo "=== BirdNET-Pi Init Container ==="
echo "Running as: $(whoami) (UID:$(id -u) GID:$(id -g))"

# Install assets as birdnetpi user
echo "Installing BirdNET assets..."
cd /opt/birdnetpi
# Use su without dash to preserve PATH environment variable
# shellcheck disable=SC2016
su birdnetpi -c "install-assets install ${BIRDNET_ASSETS_VERSION:-latest} --skip-existing"

# Set up config
echo "Setting up configuration..."
mkdir -p /var/lib/birdnetpi/config

if [ ! -f /var/lib/birdnetpi/config/birdnetpi.yaml ]; then
    echo "Creating initial config from template..."
    cp /opt/birdnetpi/config_templates/birdnetpi.yaml /var/lib/birdnetpi/config/birdnetpi.yaml
else
    echo "Config exists - preserving user settings."
fi

# Fix permissions
echo "Setting ownership to birdnetpi (UID:1000 GID:1000)..."
chown -R 1000:1000 /var/lib/birdnetpi
chmod 755 /var/lib/birdnetpi
chmod 755 /var/lib/birdnetpi/config
chmod 664 /var/lib/birdnetpi/config/birdnetpi.yaml

echo "Permissions set:"
ls -la /var/lib/birdnetpi/config/

echo "=== Init Complete ==="
