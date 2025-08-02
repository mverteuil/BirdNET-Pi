# PHP to FastAPI Migration Guide

## Overview

BirdNET-Pi has been completely migrated from PHP to FastAPI, a modern Python web framework. This migration provides better performance, improved maintainability, and seamless integration with the existing Python-based analysis components.

## What Changed

### Removed Components
- **PHP-FPM**: No longer required for web interface
- **Apache2**: Replaced by Caddy as the primary web server
- **PHP packages**: All PHP dependencies removed

### New Architecture
- **FastAPI**: Modern Python web framework serving all web interfaces
- **Caddy**: Single web server handling both static files and API proxying
- **WebSocket Support**: Real-time audio streaming and spectrogram visualization
- **Unified Backend**: All components now run in Python

## For New Installations

New installations will automatically use the FastAPI-based architecture. The installation process has been updated to:
- Skip PHP package installation
- Install only necessary Python dependencies
- Configure Caddy to proxy FastAPI application

## For Existing Installations

### Automatic Migration
Your existing BirdNET-Pi installation will continue to work. The FastAPI application runs alongside the legacy PHP components during the transition period.

### Complete PHP Removal (Optional)
To fully remove PHP components and clean up your system:

1. **Backup your configuration** (recommended):
   ```bash
   cp ~/BirdNET-Pi/birdnet.conf ~/BirdNET-Pi/birdnet.conf.backup
   ```

2. **Run the PHP removal script**:
   ```bash
   cd ~/BirdNET-Pi
   ./scripts/remove_php_components.sh
   ```

3. **Restart BirdNET-Pi services**:
   ```bash
   sudo systemctl restart birdnet*
   sudo systemctl restart caddy
   ```

### What the Removal Script Does
- Stops and disables PHP-FPM service
- Removes Apache2 if installed
- Uninstalls PHP packages and dependencies
- Cleans up configuration directories
- Removes orphaned packages

## Benefits of Migration

### Performance Improvements
- **Faster Response Times**: Native Python integration eliminates PHP-to-Python bridges
- **Lower Memory Usage**: Single Python process instead of separate PHP/Python processes
- **Better Caching**: Unified application state management

### Enhanced Features
- **Real-time WebSocket Streaming**: Live audio and spectrogram data
- **Interactive Visualizations**: Dynamic spectrogram controls and real-time updates
- **Modern API**: RESTful endpoints with automatic documentation
- **Better Error Handling**: Comprehensive error messages and logging

### Development Benefits
- **Single Language**: Entire application in Python
- **Modern Framework**: FastAPI provides automatic API documentation, validation, and testing
- **Better Testing**: Unified test suite for all components
- **Easier Maintenance**: Simplified dependency management

## Troubleshooting

### Common Issues After Migration

**Web Interface Not Loading**
- Check that FastAPI service is running: `sudo systemctl status birdnet-web`
- Verify Caddy configuration: `sudo systemctl status caddy`
- Check logs: `journalctl -u birdnet-web -f`

**Missing Features**
- All PHP functionality has been ported to FastAPI
- If you notice missing features, please report them as issues

**Performance Issues**
- FastAPI should be faster than PHP for most operations
- If experiencing slowdowns, check system resources and logs

### Rolling Back (Not Recommended)
If you need to roll back to PHP temporarily:

1. Reinstall PHP packages:
   ```bash
   sudo apt install -y php php-fpm php-sqlite3 php-curl php-xml php-zip
   ```

2. Reconfigure your web server to serve PHP files

3. Note: This is not supported and may cause conflicts

## Getting Help

- **Documentation**: Check the main README and documentation files
- **Issues**: Report problems on the GitHub issue tracker
- **Community**: Join discussions in the BirdNET-Pi community forums

## Technical Details

### Port Configuration
- **Web Interface**: Same ports as before (typically 80/443)
- **FastAPI**: Runs on port 8000 internally (proxied by Caddy)
- **WebSocket**: `/ws/audio` and `/ws/spectrogram` endpoints

### File Structure
- **Templates**: Moved to `src/birdnetpi/web/templates/`
- **Static Files**: Served directly by Caddy from existing location
- **Configuration**: Same `birdnet.conf` file format supported

### API Endpoints
FastAPI provides the same endpoints as the PHP implementation, plus new features:
- `/api/detections` - Detection data API
- `/ws/audio` - Live audio WebSocket
- `/ws/spectrogram` - Real-time spectrogram WebSocket
- `/admin` - Database administration interface

## Migration Timeline

- **Legacy Support**: ~~PHP files moved to `legacy-files/` directory~~ (REMOVED)
- **Current Version**: Full FastAPI implementation
- **Future Versions**: PHP support completely removed

This migration ensures BirdNET-Pi remains modern, maintainable, and performant for years to come.
