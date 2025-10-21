# BirdNET-Pi Release Assets - v2.2.1

This orphaned commit provides a lightweight tag for BirdNET-Pi asset release v2.2.1.

## Assets Available as Downloads

All binary assets are attached to this release as gzipped downloads to minimize repository size.

- **models.gz**: BirdNET TensorFlow Lite models for bird identification
- **ioc_reference.db.gz**: IOC World Bird Names with translations (24 languages, CC-BY-4.0)
- **wikidata_reference.db.gz**: Wikidata bird names (57 languages, CC0), images, conservation status


## Installation

These assets are automatically downloaded and decompressed during BirdNET-Pi installation.

For manual installation:

1. Download the gzipped asset files from this release's downloads
2. Decompress them: `gunzip <filename>.gz` or `tar xzf <filename>.tar.gz`
3. Place assets in the appropriate directories as specified in the documentation

## Technical Details

This release uses the orphaned commit strategy with external asset storage:
- The orphaned commit contains only this README (keeping it tiny)
- Binary assets are attached as gzipped release downloads
- Downloads are automatically decompressed during installation

Credit to Ben Webber for the orphaned commit approach.

- **Release Version**: v2.2.1
- **Asset Tag**: assets-v2.2.1
- **Created**: Automated release system
- **Compression**: gzip (level 9)
