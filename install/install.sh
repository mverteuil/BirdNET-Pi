#!/usr/bin/env bash
# This script is a simple wrapper around the main Python setup script.
# It ensures that the Python script is executed with the correct permissions
# and that the environment is properly configured.
set -e
# It is highly recommended to run this script as a non-root user with sudo privileges.
# The script will elevate permissions only when necessary.
if [  "$(id -u)" -eq 0 ]; then
    echo "This script should not be run as root. Please run as a non-root user with sudo privileges."
    exit 1
fi
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Bootstrap the environment
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Execute the main setup script, which will handle all the installation and configuration logic.
# The Python script is responsible for elevating its own permissions via `sudo` when necessary.
python3.11 "${SCRIPT_DIR}/setup_app.py"
