FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Asset version for runtime downloads (can be overridden via environment variable)
ARG BIRDNET_ASSETS_VERSION=v2.1.0

ENV DNS_SERVER=8.8.8.8
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV MPLCONFIGDIR=/var/lib/birdnetpi/config
ENV BIRDNETPI_APP=/opt/birdnetpi
ENV BIRDNETPI_DATA=/var/lib/birdnetpi
ENV BIRDNETPI_CONFIG=/var/lib/birdnetpi/config/birdnetpi.yaml

# Set shell for pipefail
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install runtime dependencies (excluding uv, as it's in the base image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    alsa-utils \
    apt-transport-https \
    avahi-utils \
    bc \
    ca-certificates \
    caddy \
    curl \
    debian-archive-keyring \
    debian-keyring \
    gnupg \
    icecast2 \
    iproute2 \
    libjpeg-dev \
    libportaudio2 \
    libsox-fmt-mp3 \
    lsof \
    memcached \
    net-tools \
    portaudio19-dev \
    pulseaudio \
    python3-systemd \
    python3-venv \
    sox \
    sqlite3 \
    supervisor \
    systemd-journal-remote \
    zlib1g-dev \
    && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy service configuration file templates
COPY config_templates/Caddyfile /etc/caddy/Caddyfile
RUN chown root:root /etc/caddy/Caddyfile
COPY config_templates/supervisord.conf /etc/supervisor/supervisord.conf

# Copy and install journald configuration to reduce SD card writes
COPY config_templates/journald.conf /etc/systemd/journald.conf
RUN chown root:root /etc/systemd/journald.conf && \
    chmod 644 /etc/systemd/journald.conf

# Create birdnetpi user and set up necessary directories
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi && \
    mkdir -p /var/run/supervisor /opt/birdnetpi /var/lib/birdnetpi/config /var/lib/birdnetpi/models /var/lib/birdnetpi/recordings /var/lib/birdnetpi/database && \
    chown -R birdnetpi:birdnetpi /var/run/supervisor /opt/birdnetpi /var/lib/birdnetpi && \
    chmod 777 /var/run/supervisor

# Switch to birdnetpi user for all application-related operations
USER birdnetpi
WORKDIR /opt/birdnetpi

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY --chown=birdnetpi:birdnetpi . /opt/birdnetpi
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Copy the configuration template for BirdNET-Pi
COPY --chown=birdnetpi:birdnetpi config_templates/birdnetpi.yaml /var/lib/birdnetpi/config/birdnetpi.yaml

# Set the asset version as an environment variable for runtime use
ENV BIRDNET_ASSETS_VERSION=${BIRDNET_ASSETS_VERSION}

# Assets are now downloaded at runtime via init container
# This reduces image size and leverages persistent volumes

# Add the BirdNET-Pi virtual environment to the PATH
ENV PATH="/opt/birdnetpi/.venv/bin:${PATH}"

# Expose the port for Caddy (8000)
EXPOSE 8000

# Command to run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-u", "birdnetpi"]
