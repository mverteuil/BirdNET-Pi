# Docker Installation Guide

This guide covers installing BirdNET-Pi using Docker containers. Docker provides a consistent, isolated environment that works across different operating systems.

## Why Choose Docker?

Docker installation is ideal if you:
- Want the simplest setup with minimal configuration
- Are running on x86_64/amd64 hardware (desktop, laptop, server)
- Need easy updates and rollbacks
- Want to avoid system-level dependencies
- Are running on Windows, macOS, or Linux desktop/server
- Want to test BirdNET-Pi without committing to a full installation

## Prerequisites

### System Requirements

- **OS**: Windows 10/11, macOS 10.15+, or Linux
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: 20GB minimum, 50GB+ recommended for extended recording
- **Audio**: USB microphone or audio interface
- **Network**: Internet connection for initial setup

### Required Software

1. **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux)
   - Windows/macOS: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Linux: [Install Docker Engine](https://docs.docker.com/engine/install/)

2. **Docker Compose** (included with Docker Desktop, separate install on Linux)

3. **Git** (to clone the repository)
   - Windows/macOS: [Download Git](https://git-scm.com/downloads)
   - Linux: `sudo apt install git` (Debian/Ubuntu) or equivalent

---

## Installation Methods

### Method 1: Using Pre-built Images (Recommended)

**Note**: Pre-built Docker images will be available from GitHub Container Registry (ghcr.io) after the first stable release. For now, use Method 2 (Building from Source).

Once available, you'll be able to pull and run pre-built images:

```bash
# Pull the latest image
docker pull ghcr.io/mverteuil/birdnet-pi:latest

# Run with docker-compose
docker compose up -d
```

### Method 2: Building from Source (Current)

During the pre-release phase, build the Docker image from source:

#### Step 1: Clone the Repository

```bash
git clone https://github.com/mverteuil/BirdNET-Pi.git
cd BirdNET-Pi
```

#### Step 2: Build the Image

```bash
docker compose build
```

This will:
- Download the base Debian image
- Install all system dependencies
- Set up the Python environment
- Download BirdNET models and assets
- Build the BirdNET-Pi application

**Note**: First build takes 10-20 minutes depending on your internet connection.

#### Step 3: Start the Services

```bash
docker compose up -d
```

The `-d` flag runs containers in the background (detached mode).

#### Step 4: Verify Installation

Check that services are running:

```bash
docker compose ps
```

You should see:
```
NAME                IMAGE               STATUS
birdnet-pi          birdnet-pi:latest   Up (healthy)
birdnet-pi-init     birdnet-pi:latest   Exited (0)
```

View logs:

```bash
docker compose logs -f birdnet-pi
```

Press `Ctrl+C` to stop viewing logs.

#### Step 5: Access the Web Interface

Open your browser and navigate to:

```
http://localhost:8000
```

Or from another device on your network:

```
http://[host-ip]:8000
```

---

## Audio Configuration

### macOS Audio Setup

BirdNET-Pi uses PulseAudio for audio. On macOS:

1. **Install PulseAudio** (if not already installed):
   ```bash
   brew install pulseaudio
   ```

2. **Configure PulseAudio** to accept network connections:

   Edit `~/.config/pulse/default.pa` or create it:
   ```bash
   mkdir -p ~/.config/pulse
   ```

   Add these lines:
   ```
   load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1
   load-module module-esound-protocol-tcp auth-ip-acl=127.0.0.1
   ```

3. **Start PulseAudio**:
   ```bash
   pulseaudio --load=module-native-protocol-tcp --exit-idle-time=-1 --daemon
   ```

4. **Verify audio devices**:
   ```bash
   pactl list sources short
   ```

### Linux Audio Setup

On Linux with PulseAudio:

1. **Ensure PulseAudio is running**:
   ```bash
   pulseaudio --check
   ```

2. **List audio sources**:
   ```bash
   pactl list sources short
   ```

3. **Docker should automatically detect** PulseAudio through `host.docker.internal`

### Windows Audio Setup

Windows audio with Docker is more complex. Consider:
- Using WSL2 (Windows Subsystem for Linux)
- PulseAudio in WSL2
- Or running BirdNET-Pi in a Linux VM

For production use on Windows, we recommend:
- Running in WSL2 with PulseAudio
- Or using a dedicated Raspberry Pi (see [SBC Installation Guide](./sbc-installation.md))

---

## Configuration

### Location and Settings

After first launch, configure your location and settings via the web interface:

1. Navigate to **Settings** → **Location**
2. Enter your GPS coordinates (latitude/longitude)
3. Set your timezone
4. Configure language preferences

### Audio Device Selection

1. Navigate to **Settings** → **Audio**
2. Select your microphone/audio input device
3. Adjust sensitivity and recording parameters
4. Test audio input

### Data Persistence

All configuration and detection data are stored in the Docker volume `birdnet-data`:

```bash
# View volume info
docker volume inspect birdnet-data

# Backup volume data
docker run --rm -v birdnet-data:/data -v $(pwd):/backup alpine tar czf /backup/birdnet-backup.tar.gz /data

# Restore from backup
docker run --rm -v birdnet-data:/data -v $(pwd):/backup alpine tar xzf /backup/birdnet-backup.tar.gz -C /
```

---

## Updating BirdNET-Pi

### Update Process (Building from Source)

To update to the latest version:

```bash
# Stop containers (NEVER use -v flag - it deletes your data!)
docker compose down

# Pull latest code
git pull

# Rebuild image
docker compose build

# Restart containers
docker compose up -d
```

**⚠️ WARNING**: **NEVER** use `docker compose down -v` as it removes all volumes including your detection data!

### Update Process (Pre-built Images)

Once pre-built images are available:

```bash
# Stop containers
docker compose down

# Pull latest image
docker compose pull

# Restart containers
docker compose up -d
```

### Database Migrations

Database migrations run automatically when containers start. You don't need to run them manually.

### Rollback to Previous Version

If an update causes issues:

```bash
# Stop containers
docker compose down

# Check out previous version
git checkout [previous-tag]

# Rebuild and restart
docker compose build
docker compose up -d
```

---

## Advanced Configuration

### Development Mode

Enable auto-reload for development:

```bash
UVICORN_RELOAD=1 docker compose up
```

This will restart the web server automatically when you modify source code.

### Custom Data Volume

Use a different data volume (useful for testing):

```bash
BIRDNET_DATA_VOLUME=birdnet-test-data docker compose up -d
```

### Home Assistant Integration

BirdNET-Pi integrates seamlessly with Home Assistant for home automation and monitoring.

#### Running Alongside Home Assistant

If you're already running Home Assistant in Docker, add BirdNET-Pi to the same Docker network:

1. **Create or use Home Assistant's network**:

```yaml
# Add to your docker-compose.yml
networks:
  homeassistant:
    external: true  # Use existing HA network
```

2. **Update BirdNET-Pi configuration**:

```yaml
services:
  birdnet-pi:
    # ... existing config ...
    networks:
      - homeassistant
      - birdnetpi-network

networks:
  homeassistant:
    external: true
  birdnetpi-network:
    driver: bridge
```

3. **Access BirdNET-Pi from Home Assistant**:
   - Internal URL: `http://birdnet-pi:8000`
   - External URL: `http://[host-ip]:8000`

#### MQTT Integration

BirdNET-Pi can publish detection events to MQTT for Home Assistant integration.

**Configuration in BirdNET-Pi** (`birdnetpi.yaml`):

```yaml
# Enable MQTT publishing
enable_mqtt: true
mqtt_broker_host: localhost  # or 'mosquitto' for HA add-on
mqtt_broker_port: 1883
mqtt_username: "your_username"
mqtt_password: "your_password"
mqtt_topic_prefix: birdnet
```

**MQTT Topics Published**:

BirdNET-Pi publishes to the following topics:
```
birdnet/detections     # Detection events
birdnet/status         # System status
birdnet/health         # Health checks
birdnet/gps            # GPS updates (if enabled)
birdnet/system         # System events
```

**Note**: Home Assistant auto-discovery is not currently implemented. You'll need to manually configure MQTT sensors in Home Assistant (see examples below).

#### Example Home Assistant Configuration

Configure sensors manually in Home Assistant's `configuration.yaml`:

```yaml
# configuration.yaml
sensor:
  - platform: rest
    name: BirdNET-Pi Recent Detections
    resource: http://birdnet-pi:8000/api/v1/detections/recent
    value_template: "{{ value_json.total }}"
    json_attributes:
      - detections
    scan_interval: 60

  - platform: mqtt
    name: "Latest Bird Detection"
    state_topic: "birdnet/detections"
    value_template: "{{ value_json.common_name }}"
    json_attributes_topic: "birdnet/detections"
```

#### Example Automations

**Notify on high-confidence bird detection**:

```yaml
automation:
  - alias: "High Confidence Bird Alert"
    trigger:
      - platform: mqtt
        topic: "birdnet/detections"
    condition:
      - condition: template
        value_template: "{{ trigger.payload_json.confidence > 0.90 }}"
    action:
      - service: notify.mobile_app
        data:
          title: "High Confidence Bird Detected!"
          message: >
            {{ trigger.payload_json.common_name }} detected
            with {{ (trigger.payload_json.confidence * 100) | round(1) }}% confidence
```

**Daily detection summary using REST API**:

```yaml
automation:
  - alias: "Daily Bird Summary"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Today's Bird Activity"
          message: >
            Check http://birdnet-pi:8000 for today's detections
```

#### Data Persistence

**Important**: BirdNET-Pi stores all configuration and detection data in the `birdnet-data` Docker volume. This data persists across:
- Container restarts
- Container updates
- Home Assistant restarts

Your detection history and settings are preserved automatically.

#### Lovelace Dashboard Card

Create a custom card to display recent detections (using the manual sensors configured above):

```yaml
type: entities
title: Recent Bird Detections
entities:
  - entity: sensor.birdnet_pi_recent_detections
  - entity: sensor.latest_bird_detection
```

Or use an iframe card to embed the BirdNET-Pi web interface:

```yaml
type: iframe
url: http://birdnet-pi:8000
aspect_ratio: 16:9
title: BirdNET-Pi Live Feed
```

#### Network Considerations

If running on the same host as Home Assistant:

1. **Avoid port conflicts**: BirdNET-Pi uses port 8000 by default
2. **Use Docker networks**: Easier than host networking
3. **Firewall rules**: Ensure MQTT port (1883) is accessible

#### Backup and Restore

Include BirdNET-Pi data in your Home Assistant backup strategy:

```bash
# Backup BirdNET-Pi volume
docker run --rm \
  -v birdnet-data:/data \
  -v /path/to/backups:/backup \
  alpine tar czf /backup/birdnetpi-$(date +%Y%m%d).tar.gz /data

# Restore from backup
docker run --rm \
  -v birdnet-data:/data \
  -v /path/to/backups:/backup \
  alpine tar xzf /backup/birdnetpi-20250123.tar.gz -C /
```

#### Supervised/OS Installations

For Home Assistant OS or Supervised installations:

**Option 1: Run on separate hardware**
- Install BirdNET-Pi on Raspberry Pi (see [SBC Installation Guide](./sbc-installation.md))
- Connect via MQTT to Home Assistant

**Option 2: Use Home Assistant's Docker**
- Access Home Assistant's Docker via SSH
- Run `docker compose` commands from SSH session
- Note: Not officially supported, may break on HA updates

**Recommended**: Run BirdNET-Pi on dedicated hardware for best reliability.

### Profiling Mode

Run with performance profiling enabled:

```bash
docker compose --profile profiling up
```

Access profiling endpoints at: `http://localhost:8001?profile=1`

### Resource Limits

Add resource limits in `docker-compose.yml`:

```yaml
services:
  birdnet-pi:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

---

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker compose logs birdnet-pi
```

Common issues:
- Port 8000 already in use: Change port in `docker-compose.yml`
- Insufficient disk space: Clean up Docker images with `docker system prune`
- Permission errors: Ensure Docker has necessary permissions

### Audio Device Not Detected

1. Verify PulseAudio is running on host
2. Check PulseAudio network settings
3. Verify `PULSE_SERVER` environment variable in `docker-compose.yml`
4. Test PulseAudio from container:
   ```bash
   docker compose exec birdnet-pi pactl list sources
   ```

### Database Migration Failures

View migration logs:
```bash
docker compose logs birdnet-pi-init
```

If migrations fail:
1. Check for sufficient disk space
2. Verify volume is mounted correctly
3. Try rebuilding: `docker compose build --no-cache`

### High CPU/Memory Usage

Monitor resource usage:
```bash
docker stats birdnet-pi
```

Optimization:
- Reduce analysis frequency in settings
- Lower audio quality settings
- Limit recording schedule to active hours
- Add resource limits (see Advanced Configuration)

### Web Interface Not Loading

1. Verify container is healthy:
   ```bash
   docker compose ps
   ```

2. Check if port 8000 is accessible:
   ```bash
   curl http://localhost:8000/api/health/ready
   ```

3. Inspect network:
   ```bash
   docker network inspect birdnetpi-network
   ```

### Cannot Access from Other Devices

1. Verify firewall allows port 8000
2. Use host IP address instead of `localhost`
3. Check Docker network configuration

---

## GitHub Container Registry (Pre-built Images)

Once stable releases are available, pre-built Docker images will be published to GitHub Container Registry:

### Pulling Images

```bash
# Pull latest release
docker pull ghcr.io/mverteuil/birdnet-pi:latest

# Pull specific version
docker pull ghcr.io/mverteuil/birdnet-pi:v2.0.0

# Pull development/nightly builds
docker pull ghcr.io/mverteuil/birdnet-pi:nightly
```

### Image Variants

- `latest` - Latest stable release (recommended for production)
- `v2.0.0` - Specific version tags (for version pinning)
- `nightly` - Latest development build (for testing new features)
- `profiling` - Development image with profiling tools

### Using GitHub Container Registry

Update `docker-compose.yml` to use pre-built images:

```yaml
services:
  birdnet-pi:
    image: ghcr.io/mverteuil/birdnet-pi:latest
    # Remove 'build' section when using pre-built images
    # ... rest of config ...
```

Then simply:
```bash
docker compose pull  # Pull latest image
docker compose up -d # Start services
```

**Benefits of pre-built images**:
- Faster deployment (no build time)
- Consistent builds across all platforms
- Automatic security updates
- Smaller download size (optimized layers)

---

## Comparison: Docker vs SBC Installation

### Choose Docker if you:
- ✅ Want the simplest setup
- ✅ Are running on x86_64/amd64 hardware
- ✅ Need easy updates and rollbacks
- ✅ Want to test before committing
- ✅ Are comfortable with containers

### Choose SBC if you:
- ✅ Want dedicated hardware for monitoring
- ✅ Need lower power consumption
- ✅ Want outdoor/remote deployment
- ✅ Need WiFi connectivity
- ✅ Want a permanent installation

See the [SBC Installation Guide](./sbc-installation.md) for Raspberry Pi and other single-board computer installations.

---

## Next Steps

After installation:

1. **[Configure Language Settings](./language-configuration.md)** - Set up multilingual species names
2. **Configure Audio** - Select microphone and adjust settings
3. **Set Location** - Configure precise GPS coordinates for accurate species detection
4. **Review Settings** - Customize analysis parameters, recording schedule, and notifications
5. **Set Up Backups** - Regularly backup your detection data

---

## Getting Help

- **Documentation**: Browse the [user documentation](./index.md)
- **Issues**: Report problems on [GitHub Issues](https://github.com/mverteuil/BirdNET-Pi/issues)
- **Docker Logs**: `docker compose logs -f birdnet-pi`
- **Community**: Join discussions on GitHub Discussions (coming soon)

---

**Note**: This installation guide covers Docker installations. For single-board computer (Raspberry Pi) installation, see the [SBC Installation Guide](./sbc-installation.md).
