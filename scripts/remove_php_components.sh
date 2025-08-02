#!/usr/bin/env bash

# BirdNET-Pi PHP Component Removal Script
# This script removes PHP dependencies that are no longer needed after migration to FastAPI
# Run this script to clean up PHP components from existing BirdNET-Pi installations

# Exit immediately if a command exits with a non-zero status
set -e

echo "BirdNET-Pi PHP Component Removal Script"
echo "======================================="
echo ""
echo "This script will remove PHP components that are no longer needed"
echo "after the migration to FastAPI."
echo ""

# Confirmation prompt
read -p "Are you sure you want to remove PHP components? This action cannot be undone. (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 0
fi

echo ""
echo "Starting PHP component removal..."

# Stop PHP-FPM service if running
echo "Stopping PHP-FPM service (if running)..."
if systemctl is-active --quiet php7.4-fpm 2>/dev/null; then
    sudo systemctl stop php7.4-fpm
    sudo systemctl disable php7.4-fpm
    echo "  - Stopped and disabled php7.4-fpm"
elif systemctl is-active --quiet php8.1-fpm 2>/dev/null; then
    sudo systemctl stop php8.1-fpm
    sudo systemctl disable php8.1-fpm
    echo "  - Stopped and disabled php8.1-fpm"
elif systemctl is-active --quiet php-fpm 2>/dev/null; then
    sudo systemctl stop php-fpm
    sudo systemctl disable php-fpm
    echo "  - Stopped and disabled php-fpm"
else
    echo "  - No PHP-FPM service found running"
fi

# Remove Apache2 if installed (as it was used for PHP hosting)
echo "Checking for Apache2..."
if command -v apache2 &> /dev/null; then
    echo "  - Apache2 found. Stopping and removing..."
    sudo systemctl stop apache2 2>/dev/null || true
    sudo systemctl disable apache2 2>/dev/null || true
    sudo apt remove --purge -y apache2 apache2-utils apache2-bin apache2.2-common 2>/dev/null || true
    sudo apt autoremove -y 2>/dev/null || true
    echo "  - Apache2 removed"
else
    echo "  - Apache2 not found (already removed or never installed)"
fi

# Remove PHP packages
echo "Removing PHP packages..."
PHP_PACKAGES=(
    "php"
    "php-fpm"
    "php-sqlite3"
    "php-curl"
    "php-xml"
    "php-zip"
    "php-common"
    "php-cli"
    "libapache2-mod-php"
)

for package in "${PHP_PACKAGES[@]}"; do
    if dpkg -l "$package" &> /dev/null; then
        echo "  - Removing $package..."
        sudo apt remove --purge -y "$package" 2>/dev/null || echo "    Warning: Could not remove $package"
    else
        echo "  - $package not installed"
    fi
done

# Remove version-specific PHP packages (common versions)
echo "Removing version-specific PHP packages..."
for version in "7.4" "8.0" "8.1" "8.2"; do
    VERSION_PACKAGES=(
        "php${version}"
        "php${version}-fpm"
        "php${version}-sqlite3"
        "php${version}-curl"
        "php${version}-xml"
        "php${version}-zip"
        "php${version}-common"
        "php${version}-cli"
        "libapache2-mod-php${version}"
    )

    for package in "${VERSION_PACKAGES[@]}"; do
        if dpkg -l "$package" &> /dev/null; then
            echo "  - Removing $package..."
            sudo apt remove --purge -y "$package" 2>/dev/null || echo "    Warning: Could not remove $package"
        fi
    done
done

# Clean up configuration files and directories
echo "Cleaning up PHP configuration directories..."
PHP_DIRS=(
    "/etc/php"
    "/var/lib/php"
    "/usr/share/php"
    "/var/log/php*"
)

for dir in "${PHP_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "  - Removing $dir..."
        sudo rm -rf "$dir" 2>/dev/null || echo "    Warning: Could not remove $dir"
    fi
done

# Remove Apache configuration directories
echo "Cleaning up Apache configuration directories..."
APACHE_DIRS=(
    "/etc/apache2"
    "/var/lib/apache2"
    "/var/log/apache2"
    "/usr/share/apache2"
)

for dir in "${APACHE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "  - Removing $dir..."
        sudo rm -rf "$dir" 2>/dev/null || echo "    Warning: Could not remove $dir"
    fi
done

# Autoremove orphaned packages
echo "Removing orphaned packages..."
sudo apt autoremove -y

# Update package cache
echo "Updating package cache..."
sudo apt update

echo ""
echo "PHP component removal completed successfully!"
echo ""
echo "Summary of changes:"
echo "  - Removed PHP and related packages"
echo "  - Removed Apache2 web server"
echo "  - Cleaned up configuration directories"
echo "  - Removed orphaned packages"
echo ""
echo "BirdNET-Pi now runs exclusively on FastAPI."
echo "The web interface is now served by Caddy on the same ports as before."
echo ""
echo "You may need to restart your system or BirdNET-Pi services for all changes to take effect."
