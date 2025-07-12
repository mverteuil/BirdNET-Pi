# Use a Debian-based image as a base
FROM debian:bullseye-slim

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt update && apt upgrade -y && \
    apt install -y --no-install-recommends \
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
    ffmpeg \
    sqlite3 \
    php \
    php-fpm \
    php-curl \
    php-xml \
    php-zip \
    icecast2 \
    caddy && \
    rm -rf /var/lib/apt/lists/*

# Copy the BirdNET-Pi application code
COPY . /app

# Create a dedicated user for BirdNET-Pi
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi

# Set permissions for the application directory
RUN chown -R birdnetpi:birdnetpi /app

# Switch to the birdnetpi user
USER birdnetpi

# Create and activate a Python virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port for FastAPI (assuming it runs on 8000)
EXPOSE 8000

# Command to run the FastAPI application
CMD ["python3", "-m", "uvicorn", "src.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
