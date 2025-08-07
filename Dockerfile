FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Set release version for asset downloads (this can be overridden via build arg)
ARG BIRDNET_ASSETS_VERSION=v1.0.2

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
    sqlite3 \
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
    python3-venv \
    supervisor \
    caddy \
    iproute2 \
    libportaudio2 \
    portaudio19-dev \
    systemd-journal-remote \
    && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy service configuration file templates
COPY config_templates/Caddyfile /etc/caddy/Caddyfile
RUN chown root:root /etc/caddy/Caddyfile
COPY config_templates/supervisord.conf /etc/supervisor/supervisord.conf

# Create birdnetpi user and set up necessary directories
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi && \
    mkdir -p /var/log/birdnetpi /var/run/supervisor /opt/birdnetpi /var/lib/birdnetpi/config /var/lib/birdnetpi/models /var/lib/birdnetpi/recordings /var/lib/birdnetpi/database && \
    chmod 777 /var/log && \
    chown -R birdnetpi:birdnetpi /var/log/birdnetpi /var/run/supervisor /opt/birdnetpi /var/lib/birdnetpi && \
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

ENV BIRDNET_ASSETS_VERSION=${BIRDNET_ASSETS_VERSION}

# Download release assets with Docker cache based on version
# This layer will be cached as long as the version doesn't change
# Download and install assets using cache
USER root
RUN --mount=type=cache,target=/tmp/asset-cache,id=birdnet-assets \
    echo "Installing BirdNET assets version: ${BIRDNET_ASSETS_VERSION}" && \
    mkdir -p /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/models && \
    mkdir -p /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/database && \
    chown -R birdnetpi:birdnetpi /tmp/asset-cache && \
    if [ -d "/tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/models" ] && [ -n "$(ls -A /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/models 2>/dev/null)" ] && \
       [ -d "/tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/database" ] && [ -f "/tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/database/ioc_reference.db" ]; then \
        echo "Using cached assets for version ${BIRDNET_ASSETS_VERSION}" && \
        mkdir -p /var/lib/birdnetpi/models && \
        mkdir -p /var/lib/birdnetpi/database && \
        cp -r /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/models/* /var/lib/birdnetpi/models/ && \
        cp -r /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/database/* /var/lib/birdnetpi/database/ && \
        chown -R birdnetpi:birdnetpi /var/lib/birdnetpi && \
        echo "Assets restored from cache successfully"; \
    else \
        echo "No cache found for version ${BIRDNET_ASSETS_VERSION}, downloading fresh assets" && \
        su birdnetpi -c "cd /opt/birdnetpi && uv run asset-installer install \"${BIRDNET_ASSETS_VERSION}\" --include-models --include-ioc-db" && \
        cp -r /var/lib/birdnetpi/models/* /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/models/ && \
        cp -r /var/lib/birdnetpi/database/* /tmp/asset-cache/${BIRDNET_ASSETS_VERSION}/database/ && \
        echo "Assets cached for future builds"; \
    fi

# Switch back to birdnetpi user
USER birdnetpi

# Add the BirdNET-Pi virtual environment to the PATH
ENV PATH="/opt/birdnetpi/.venv/bin:${PATH}"

# Expose the port for Caddy (8000)
EXPOSE 8000

# Command to run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-u", "birdnetpi"]
