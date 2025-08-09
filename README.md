# BirdNET-Pi Release Assets - v2.1.0

This branch contains binary assets for BirdNET-Pi version v2.1.0.

## Assets Included

- **data/models**: BirdNET TensorFlow Lite models for bird identification
- **data/database/ioc_reference.db**: IOC World Bird Names reference database
- **data/database/avibase_database.db**: Avibase multilingual bird names database (Lepage 2018, CC-BY-4.0)
- **data/database/patlevin_database.db**: BirdNET label translations compiled by Patrick Levin

## Installation

These assets are automatically downloaded during BirdNET-Pi installation.
For manual installation:

1. Clone the main BirdNET-Pi repository
2. Download assets from this tagged release
3. Place assets in the appropriate directories as specified in the documentation

## Technical Details

This release uses the orphaned commit strategy to distribute large binary files
without bloating the main repository history. Credit to Ben Webber for this approach.

- **Release Version**: v2.1.0
- **Asset Tag**: assets-v2.1.0
- **Created**: Automated release system
