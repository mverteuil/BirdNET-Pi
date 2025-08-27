# Stage 1: Create a clean git repository with current working files
# This approach:
# - Uses the local .git to preserve remote configuration
# - Includes uncommitted changes from working directory
# - Creates a minimal git repo without bloated history
# - Allows testing local changes without committing first
FROM alpine/git:v2.45.2 AS git-stage

WORKDIR /source
# Copy everything including .git (temporarily, just for this stage)
COPY . /source/

# Create a new repo with just the working directory state
WORKDIR /repo

# Git repository URL (can be overridden at build time)
# Placed here to minimize cache invalidation - only affects the RUN command below
ARG GIT_REPOSITORY_URL=https://github.com/mverteuil/BirdNET-Pi.git

# Optimized: Combine all git operations in a single layer
RUN cp -r /source/* . 2>/dev/null || true && \
    cp -r /source/.??* . 2>/dev/null || true && \
    rm -rf .git && \
    git init && \
    git --git-dir=/source/.git remote get-url origin > /tmp/remote_url 2>/dev/null || echo "${GIT_REPOSITORY_URL}" > /tmp/remote_url && \
    git remote add origin "$(cat /tmp/remote_url)" && \
    git add -A && \
    git config user.email "docker@build" && \
    git config user.name "Docker Build" && \
    git commit -m "Docker build snapshot with working directory changes" && \
    git config --add safe.directory /repo && \
    rm -f /tmp/remote_url

# Stage 2: Main application (runtime)
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS runtime

# Asset version for runtime downloads (can be overridden via environment variable)
ARG BIRDNET_ASSETS_VERSION=v2.1.0

# Combine ENV declarations for better layer efficiency
ENV DNS_SERVER=8.8.8.8 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MPLCONFIGDIR=/var/lib/birdnetpi/config \
    BIRDNETPI_APP=/opt/birdnetpi \
    BIRDNETPI_DATA=/var/lib/birdnetpi \
    BIRDNETPI_CONFIG=/var/lib/birdnetpi/config/birdnetpi.yaml

# Set shell for pipefail
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# OPTIMIZATION: Combine package installation and cleanup in single layer
# This reduces the image size by ~100MB
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
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
    git \
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
    zlib1g-dev && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    # Remove unnecessary files to reduce size
    find /usr/share/doc -depth -type f ! -name copyright -delete && \
    find /usr/share/doc -empty -delete && \
    rm -rf /usr/share/man/* /usr/share/groff/* /usr/share/info/*

# Copy service configuration files with proper permissions
COPY --chmod=644 config_templates/Caddyfile /etc/caddy/Caddyfile
COPY --chmod=644 config_templates/supervisord.conf /etc/supervisor/supervisord.conf
COPY --chmod=644 config_templates/journald.conf /etc/systemd/journald.conf

# Create birdnetpi user and set up necessary directories
RUN useradd -m -s /bin/bash birdnetpi && \
    usermod -aG audio,video,dialout birdnetpi && \
    mkdir -p /var/run/supervisor /opt/birdnetpi /var/lib/birdnetpi/{config,models,recordings,database} && \
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

# Copy the project source code with clean git repository from stage 1
# This gives us git functionality without the bloated history
COPY --from=git-stage --chown=birdnetpi:birdnetpi /repo /opt/birdnetpi

# Install the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Configure git safe directory for the birdnetpi user
RUN git config --global --add safe.directory /opt/birdnetpi

# Copy the configuration template to a location that won't be overlaid by volume mount
# The init container will copy this to the volume
COPY --chown=birdnetpi:birdnetpi config_templates/birdnetpi.yaml /opt/birdnetpi/config_templates/birdnetpi.yaml

# Set the asset version as an environment variable for runtime use
ENV BIRDNET_ASSETS_VERSION=${BIRDNET_ASSETS_VERSION}

# Assets are now downloaded at runtime via init container
# This reduces image size and leverages persistent volumes

# Add the BirdNET-Pi virtual environment to the PATH
ENV PATH="/opt/birdnetpi/.venv/bin:${PATH}"

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose the port for Caddy (8000)
EXPOSE 8000

# Default command to run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-u", "birdnetpi"]

# ============================================================================
# Init stage - for permission setup (runs as root)
# ============================================================================
FROM runtime AS init

# Switch back to root for init operations
USER root

# Init container entrypoint script
# Create init script using printf to avoid heredoc issues with hadolint
# hadolint ignore=DL3059
RUN printf '#!/bin/bash\n\
set -e\n\
\n\
echo "=== BirdNET-Pi Init Container ==="\n\
echo "Running as: $(whoami) (UID:$(id -u) GID:$(id -g))"\n\
\n\
# Install assets as birdnetpi user\n\
echo "Installing BirdNET assets..."\n\
cd /opt/birdnetpi\n\
# Use su without dash to preserve PATH environment variable\n\
su birdnetpi -c "install-assets install ${BIRDNET_ASSETS_VERSION:-v2.1.0} --skip-existing"\n\
\n\
# Set up config\n\
echo "Setting up configuration..."\n\
mkdir -p /var/lib/birdnetpi/config\n\
\n\
if [ ! -f /var/lib/birdnetpi/config/birdnetpi.yaml ]; then\n\
    echo "Creating initial config from template..."\n\
    cp /opt/birdnetpi/config_templates/birdnetpi.yaml /var/lib/birdnetpi/config/birdnetpi.yaml\n\
else\n\
    echo "Config exists - preserving user settings."\n\
fi\n\
\n\
# Fix permissions\n\
echo "Setting ownership to birdnetpi (UID:1000 GID:1000)..."\n\
chown -R 1000:1000 /var/lib/birdnetpi\n\
chmod 755 /var/lib/birdnetpi\n\
chmod 755 /var/lib/birdnetpi/config\n\
chmod 664 /var/lib/birdnetpi/config/birdnetpi.yaml\n\
\n\
echo "Permissions set:"\n\
ls -la /var/lib/birdnetpi/config/\n\
\n\
echo "=== Init Complete ==="\n\
' > /init.sh

RUN chmod +x /init.sh

# Use the init script as entrypoint
ENTRYPOINT ["/init.sh"]
