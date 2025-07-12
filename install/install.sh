#!/usr/bin/env bash

# This script handles the foundational environment setup for BirdNET-Pi.
# It should be run with sudo privileges.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting BirdNET-Pi foundational environment setup..."

# Update package lists and upgrade existing packages
echo "Updating package lists and upgrading existing packages..."
sudo apt update && sudo apt upgrade -y

# Install essential build tools and dependencies
echo "Installing essential build tools and dependencies..."
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    unzip \
    cmake \
    make \
    bc \
    libjpeg-dev \
    zlib1g-dev \
    python3-dev \
    python3-pip \
    python3-venv \
    lsof \
    net-tools \
    alsa-utils \
    pulseaudio \
    avahi-utils \
    sox \
    libsox-fmt-mp3 \
    ffmpeg

# Install Caddy (if not already installed via apt)
# This part might need adjustment based on how Caddy is officially distributed for Debian/Raspbian
if ! command -v caddy &> /dev/null
then
    echo "Installing Caddy..."
    sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt update
    sudo apt install -y caddy
fi

# Install SQLite3 and PHP dependencies (for backward compatibility/migration if needed)
echo "Installing SQLite3 and PHP dependencies..."
sudo apt install -y sqlite3 php-sqlite3 php php-fpm php-curl php-xml php-zip

# Install Icecast2
echo "Installing Icecast2..."
echo "icecast2 icecast2/icecast-setup boolean false" | sudo debconf-set-selections
sudo apt install -y icecast2

# Create a dedicated user for BirdNET-Pi if it doesn't exist
# This assumes the user will be 'birdnetpi' for consistency
if ! id "birdnetpi" &>/dev/null;
then
    echo "Creating birdnetpi user..."
    sudo useradd -m -s /bin/bash birdnetpi
    # Add birdnetpi user to necessary groups (e.g., audio, video, dialout)
    sudo usermod -aG audio,video,dialout birdnetpi
fi

# Function to download model files from GitHub Releases
download_model_files() {
    echo "Downloading BirdNET-Pi model files..."
    local github_owner="mverteuil"
    local github_repo="BirdNET-Pi"
    local release_tag="models-v1.0.0"
    local model_filenames=(
        "BirdNET_6K_GLOBAL_MODEL.tflite"
        "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite"
        "BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite"
        "labels_l18n.zip"
        "labels_lang.txt"
        "labels_nm.zip"
    )
    local model_dir="${HOME}/BirdNET-Pi/model"

    # Create model directory if it doesn't exist
    sudo -u birdnetpi mkdir -p "${model_dir}"

    for model_file in "${model_filenames[@]}"; do
        local download_url="https://github.com/${github_owner}/${github_repo}/releases/download/${release_tag}/${model_file}"
        local destination_path="${model_dir}/${model_file}"

        if [ ! -f "${destination_path}" ]; then
            echo "Downloading ${model_file} from ${download_url}"
            sudo -u birdnetpi wget -q --show-progress -O "${destination_path}" "${download_url}"
            echo "Download complete."
        else
            echo "${model_file} already exists. Skipping download."
        fi
    done
}

# Call the function to download model files
download_model_files

echo "Foundational environment setup complete."
