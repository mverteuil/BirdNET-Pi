# Stage 1: Builder
FROM debian:bullseye as builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build-time dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    unzip \
    python3-dev \
    python3-venv \
    && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create birdnetpi user for consistent permissions during build
RUN useradd -m -s /bin/bash birdnetpi


# Stage 2: Runtime
FROM debian:bullseye-slim

ENV DNS_SERVER=8.8.8.8

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Set shell for pipefail
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    sqlite3 \
    php \
    php-fpm \
    php-curl \
    php-xml \
    php-zip \
    icecast2 \
    lsof \
    net-tools \
    alsa-utils \
    pulseaudio \
    avahi-utils \
    sox \
    libsox-fmt-mp3 \
    bc \
    libjpeg-dev \
    zlib1g-dev \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    gnupg \
    curl \
    ca-certificates \
    python3 \
    python3-venv \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install uv globally in runtime stage
RUN curl -Lsf https://github.com/astral-sh/uv/releases/download/0.7.20/uv-aarch64-unknown-linux-gnu.tar.gz -o /tmp/uv.tar.gz && \
    tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1 && \
    rm /tmp/uv.tar.gz

ARG TARGETARCH

# Install Caddy
RUN case "${TARGETARCH}" in     "amd64") CADDY_ARCH="amd64" ;;     "arm64") CADDY_ARCH="arm64" ;;     *) echo "Unsupported architecture: ${TARGETARCH}"; exit 1 ;;     esac &&     curl -L https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_linux_${CADDY_ARCH}.deb -o /tmp/caddy.deb &&     dpkg -i /tmp/caddy.deb &&     rm /tmp/caddy.deb &&     apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create dedicated user for BirdNET-Pi and set up directories/permissions
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi && \
    mkdir -p /var/log /app/tmp && \
    chmod 777 /var/log && \
    chown birdnetpi:birdnetpi /app/tmp

# Copy application code to runtime stage
COPY . /app
RUN chown -R birdnetpi:birdnetpi /app && chmod +x /app/start.sh
RUN ls -l /app/start.sh

# Switch to the birdnetpi user and set up Python environment
USER birdnetpi
WORKDIR /app
ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"
ENV TMPDIR=/app/tmp

RUN /usr/local/bin/uv sync --no-cache

# Copy Caddyfile template and start script
COPY etc/Caddyfile.template /etc/caddy/Caddyfile
COPY start.sh /app/start.sh

# Expose the port for Caddy (80)
EXPOSE 80

# Command to run the start script
CMD ["bash", "/app/start.sh"]
