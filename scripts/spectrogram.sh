#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Execute the Python wrapper for ReportingManager's spectrogram logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/reporting_manager_wrapper.py spectrogram --audio_file "$1" --output_image "$2"
