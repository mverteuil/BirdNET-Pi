#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Source the birdnet.conf to get environment variables
# shellcheck disable=SC1091
source /etc/birdnet/birdnet.conf

# Execute the Python wrapper for UpdateManager's update_caddyfile logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/update_manager_wrapper.py update_caddyfile "$@"
