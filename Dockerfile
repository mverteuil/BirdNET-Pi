FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV DNS_SERVER=8.8.8.8
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

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
    && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy service configuration file templates
COPY config_templates/Caddyfile.template /etc/caddy/Caddyfile
RUN chown root:root /etc/caddy/Caddyfile
COPY config_templates/supervisor/supervisord.conf /etc/supervisor/supervisord.conf

# Create birdnetpi user and set up necessary directories
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi && \
    mkdir -p /var/log /app/tmp /var/log/supervisor /var/log/birdnet && \
    chmod 777 /var/log && \
    chown birdnetpi:birdnetpi /app/tmp /var/log/supervisor /var/log/birdnet && \
    mkdir -p /var/run/supervisor &&     chown birdnetpi:birdnetpi /var/run/supervisor &&     chmod 777 /var/run/supervisor &&     mkdir -p /app &&     chown birdnetpi:birdnetpi /app

# Switch to birdnetpi user for all application-related operations
USER birdnetpi
WORKDIR /app

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY --chown=birdnetpi:birdnetpi . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Copy the configuration template for BirdNET-Pi
COPY --chown=birdnetpi:birdnetpi config_templates/birdnet_pi_config.yaml.template /app/config/birdnet_pi_config.yaml

# Add the BirdNET-Pi virtual environment to the PATH
ENV PATH="/app/.venv/bin:${PATH}"

# Expose the port for Caddy (8000)
EXPOSE 8000

# Command to run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-u", "birdnetpi"]
