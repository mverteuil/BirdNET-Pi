#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Execute the Python wrapper for ServiceManager's stop_service logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/service_manager_wrapper.py stop_service "$@"
