# BirdNET-Pi User Guide

Welcome to the BirdNET-Pi user documentation. This guide covers installation, configuration, and multilingual support for BirdNET-Pi.

## Getting Started

### Installation

**[SBC Installation Guide](./sbc-installation.md)**

Install BirdNET-Pi on Raspberry Pi or other single-board computers. Choose your method:
- **Attended Installation (Recommended)**: Use Raspberry Pi Imager and run the installer interactively
- **Unattended Installation (Advanced)**: Pre-configure everything for completely headless setup
- Flash single or multiple SD cards with the built-in flasher tool
- Includes hardware recommendations and troubleshooting

**[Docker Installation Guide](./docker-installation.md)**

Install BirdNET-Pi using Docker containers on Windows, macOS, or Linux:
- Simple setup with Docker Compose
- Pre-built images from GitHub Container Registry (coming soon)
- Build from source for development
- Audio configuration for different platforms
- Easy updates and rollbacks

### Additional Configuration

**[Boot Volume Pre-Configuration](./boot-config.md)**

Pre-configure BirdNET-Pi settings before first boot (advanced):
- Pre-configure device settings on the SD card
- Set up location coordinates and timezone
- Choose your language preference
- Configure for completely headless operation

### Internationalization

**[Language Configuration](./language-configuration.md)**

Set up multilingual support for bird species names. This comprehensive guide covers:
- Quick start configuration examples
- Supported language codes and database coverage
- Understanding translation precedence (IOC, PatLevin, Avibase)
- Troubleshooting language configuration issues
- Regional language variants

## Quick Reference

### For New Users

1. **Choose Installation Method**:
   - [SBC Installation](./sbc-installation.md) for Raspberry Pi and similar devices
   - [Docker Installation](./docker-installation.md) for Windows, macOS, or Linux
2. **Complete Setup**: Follow the interactive installer or pre-configure for headless operation
3. **Configure Location**: Set your GPS coordinates for accurate species detection
4. **Choose Your Language**: Set your preferred language for species names (see [Language Configuration](./language-configuration.md))
5. **Start Monitoring**: Access the web interface and begin detecting birds!

### Configuration Files

**Main Configuration** (`birdnetpi.yaml`):
```yaml
# Device identification
device_name: My BirdNET Station

# Location (required for accurate species detection)
latitude: 40.7128
longitude: -74.0060
timezone: America/New_York

# Language for UI and species names
language: en
```

### Common Language Configurations

| Language | Code | Configuration |
|----------|------|---------------|
| English | `en` | `language: en` |
| Spanish | `es` | `language: es` |
| French | `fr` | `language: fr` |
| German | `de` | `language: de` |
| Portuguese | `pt` | `language: pt` |
| Dutch | `nl` | `language: nl` |
| Italian | `it` | `language: it` |
| Japanese | `ja` | `language: ja` |
| Chinese | `zh` | `language: zh` |

## Support and Troubleshooting

### Common Issues

**Species names not translating?**
- Verify your language code is correct (e.g., `es`, not `spanish`)
- Check if your language has coverage for detected species
- Some rare species may only have English names

**Configuration not taking effect?**
- Restart the system after changing configuration
- Verify configuration file syntax is valid YAML
- Check system logs for configuration errors

### Getting Help

For additional support:
- Check the troubleshooting sections in each guide
- Review configuration examples for your specific setup
- Consult the main BirdNET-Pi documentation for general usage

---

**Note**: This documentation focuses on user-facing configuration and setup.
