#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Execute the Python wrapper for AudioManager's custom_recording logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/audio_manager_wrapper.py custom_record --duration "$1" --output_file "$2"
