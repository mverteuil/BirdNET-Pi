# Boot Volume Pre-Configuration

BirdNET-Pi supports pre-configuration via a text file placed on the boot volume. This is useful for headless installations where you want to configure the system before first boot.

## Creating a Boot Configuration File

Create a file named `birdnetpi_config.txt` in the `/boot/firmware/` directory with your desired configuration values:

```
# BirdNET-Pi Boot Configuration
# Lines starting with # are comments and will be ignored

# Device identification
device_name=My BirdNET Station

# Geographic location (required for species detection)
latitude=40.7128
longitude=-74.0060
timezone=America/New_York

# Language for species names (ISO 639-1 code)
language=en
```

## Configuration Options

### Required for Optimal Performance

- `latitude` - Decimal degrees (e.g., `40.7128`)
- `longitude` - Decimal degrees (e.g., `-74.0060`)
- `timezone` - IANA timezone name (e.g., `America/New_York`, `Europe/London`)

### Optional

- `device_name` - Friendly name for your device (default: `BirdNET-Pi`)
- `language` - Language code for species names (default: `en`)
  - Supported languages determined by IOC database translations
  - Common options: `en`, `es`, `fr`, `de`, `it`, `pt`, `nl`, `ru`, `zh`, `ja`

## How It Works

1. **Flasher Integration**: When flashing an SD card with BirdNET-Pi, place this file in the boot partition
2. **First Boot**: On first boot, `setup-system` reads this file
3. **Auto-Configuration**: Values from the file are used instead of prompting
4. **Fallback**: If the file doesn't exist or values are missing, the system will:
   - Auto-detect GPS location (if GPS hardware present)
   - Auto-detect audio devices
   - Prompt for missing values (if in attended install mode)

## Priority of Configuration Sources

The setup system uses this priority order:

1. **GPS Detection** - If GPS hardware is present and gets a fix
2. **Boot Config File** - Values from `/boot/firmware/birdnetpi_config.txt`
3. **User Prompts** - Interactive prompts (only in attended installs)
4. **Defaults** - Fallback defaults if nothing else available

## Example: Headless Installation

For a completely headless installation:

```bash
# 1. Flash SD card with BirdNET-Pi image
# 2. Mount the boot partition
# 3. Create configuration file
cat > /path/to/boot/firmware/birdnetpi_config.txt <<EOF
device_name=Backyard Station
latitude=51.5074
longitude=-0.1278
timezone=Europe/London
language=en
EOF
# 4. Unmount and boot the Pi
```

The system will configure itself automatically without any user interaction.

## Validation

- **Timezone**: Must be a valid IANA timezone (validated against `pytz.common_timezones`)
- **Language**: Must be a supported language code (validated against IOC database)
- **Coordinates**: Must be valid decimal degrees
  - Latitude: -90 to 90
  - Longitude: -180 to 180

## Finding Your Configuration Values

### Latitude and Longitude

- Use [latlong.net](https://www.latlong.net/) to find your coordinates
- Or check Google Maps by right-clicking your location

### Timezone

- See [Wikipedia: List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
- Examples:
  - Americas: `America/New_York`, `America/Chicago`, `America/Los_Angeles`
  - Europe: `Europe/London`, `Europe/Paris`, `Europe/Berlin`
  - Asia: `Asia/Tokyo`, `Asia/Shanghai`, `Asia/Kolkata`
  - Pacific: `Pacific/Auckland`, `Australia/Sydney`

### Language Codes

Run `setup-system` interactively once to see all supported languages with their species counts, or check the [IOC World Bird List](https://www.worldbirdnames.org/) for language availability.
