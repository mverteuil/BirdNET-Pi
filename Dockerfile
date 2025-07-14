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
ARG TARGETARCH

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
    python3-venv     supervisor     && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh &&     mv /root/.local/bin/uv /usr/local/bin/uv

COPY scripts/install_deps.sh /usr/local/bin/install_deps.sh
RUN chmod +x /usr/local/bin/install_deps.sh && install_deps.sh

# Create dedicated user for BirdNET-Pi and set up directories/permissions
RUN useradd -m -s /bin/bash birdnetpi &&     usermod -aG audio,video,dialout birdnetpi &&     mkdir -p /var/log /app/tmp /var/log/supervisor &&     chmod 777 /var/log &&     chown birdnetpi:birdnetpi /app/tmp /var/log/supervisor

RUN mkdir -p /var/run/supervisor && chown birdnetpi:birdnetpi /var/run/supervisor

# Copy application code to runtime stage
COPY . /app
RUN chown -R birdnetpi:birdnetpi /app

# Switch to the birdnetpi user and set up Python environment
USER birdnetpi
WORKDIR /app
ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"
ENV TMPDIR=/app/tmp

RUN /usr/local/bin/uv sync --no-cache

# Copy Caddyfile and supervisor config
USER root
COPY scripts/setup_configs.sh /usr/local/bin/setup_configs.sh
RUN chmod +x /usr/local/bin/setup_configs.sh && setup_configs.sh
USER birdnetpi

# Expose the port for Caddy (80)
EXPOSE 80

# Command to run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
