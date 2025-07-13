#!/bin/bash
set -e

# This script sets up the runtime configuration for BirdNET-Pi inside the Docker container.
# It copies configuration templates to their runtime location and creates necessary symlinks.

APP_DIR="/app"
TEMPLATE_DIR="${APP_DIR}/config_templates"
CONFIG_DIR="${APP_DIR}/config"

# 1. Create the runtime config directory
echo "Creating runtime config directory at ${CONFIG_DIR}"
mkdir -p "${CONFIG_DIR}"

# 2. Copy templates to runtime config files, stripping the .template suffix
echo "Copying configuration templates..."
for template in "${TEMPLATE_DIR}"/*.template; do
    if [ -f "$template" ]; then
        filename=$(basename "$template" .template)
        cp "$template" "${CONFIG_DIR}/${filename}"
        echo "Copied ${template} to ${CONFIG_DIR}/${filename}"
    fi
done

# Handle supervisor config separately as it's in a subdirectory
SUPERVISOR_TEMPLATE_DIR="${TEMPLATE_DIR}/supervisor"
SUPERVISOR_CONFIG_DIR="${CONFIG_DIR}/supervisor"
mkdir -p "${SUPERVISOR_CONFIG_DIR}"
if [ -f "${SUPERVISOR_TEMPLATE_DIR}/supervisord.conf" ]; then
    cp "${SUPERVISOR_TEMPLATE_DIR}/supervisord.conf" "${SUPERVISOR_CONFIG_DIR}/supervisord.conf"
    echo "Copied supervisor config."
fi

# 3. Set ownership for the new config files
echo "Setting ownership for ${CONFIG_DIR}"
chown -R birdnetpi:birdnetpi "${CONFIG_DIR}"

# 4. Create system directories for symlinks
echo "Creating system directories for symlinks..."
mkdir -p /etc/caddy
mkdir -p /etc/supervisor/conf.d

# 5. Create symlinks from system paths to the runtime configs
echo "Creating symlinks..."
ln -sf "${CONFIG_DIR}/Caddyfile" /etc/caddy/Caddyfile
ln -sf "${CONFIG_DIR}/supervisor/supervisord.conf" /etc/supervisor/conf.d/supervisord.conf

echo "Configuration setup complete."
