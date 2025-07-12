#!/bin/bash

# This is a minimal wrapper script. The core logic will be migrated to Python.

# Execute the Python wrapper for UpdateManager's update_birdnet_snippets logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/update_manager_wrapper.py update_birdnet_snippets "$@"
