#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Execute the Python wrapper for AnalysisManager's extract_new_birdsounds logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/analysis_manager_wrapper.py extract_new_birdsounds "$@"
