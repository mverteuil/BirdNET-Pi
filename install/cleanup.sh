#!/usr/bin/env bash
# BirdNET-Pi Installation Cleanup Script
#
# Usage: sudo bash cleanup.sh
#
# This script removes all files, directories, services, and users
# created by the BirdNET-Pi installer.

set -e

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Use: sudo bash cleanup.sh"
    exit 1
fi

echo "=========================================="
echo "BirdNET-Pi Cleanup"
echo "=========================================="
echo ""
echo "This will remove:"
echo "  - All BirdNET-Pi systemd services"
echo "  - /opt/birdnetpi directory"
echo "  - /var/lib/birdnetpi directory"
echo "  - /var/log/birdnetpi directory"
echo "  - birdnetpi user"
echo "  - /tmp/birdnet-installer directory"
echo ""
echo "System packages (Redis, Caddy, etc.) will remain installed."
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Stopping BirdNET services..."
# List of services to stop
SERVICES=(
    "birdnet_fastapi.service"
    "birdnet_pulseaudio.service"
    "birdnet_audio_capture.service"
    "birdnet_audio_analysis.service"
    "birdnet_audio_websocket.service"
    "birdnet_update.service"
)

for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo "  Stopping $service..."
        systemctl stop "$service" --no-block 2>/dev/null || true
    fi
done

# Give services a moment to stop
sleep 2

echo "Disabling BirdNET services..."
for service in "${SERVICES[@]}"; do
    systemctl disable "$service" 2>/dev/null || true
done

echo "Removing service files..."
rm -f /etc/systemd/system/birdnet_*.service
systemctl daemon-reload

echo "Stopping system services..."
systemctl stop redis-server 2>/dev/null || true
systemctl stop caddy 2>/dev/null || true

echo "Removing directories..."
rm -rf /opt/birdnetpi
rm -rf /var/lib/birdnetpi
rm -rf /var/log/birdnetpi
rm -rf /tmp/birdnet-installer

echo "Removing birdnetpi user..."
userdel -r birdnetpi 2>/dev/null || true

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
echo ""
echo "System packages (Redis, Caddy, etc.) are still installed."
echo "Redis and Caddy services have been stopped."
echo ""
echo "To restart system services:"
echo "  sudo systemctl start redis-server"
echo "  sudo systemctl start caddy"
echo ""
