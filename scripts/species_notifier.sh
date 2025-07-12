#!/bin/bash

# This is a minimal wrapper script. The core logic has been migrated to Python.

# Execute the Python wrapper for NotificationService's species_notifier logic
python3 /Users/mdeverteuil/Documents/Codebase/birdnet-exploration/BirdNET-Pi/src/notification_service_wrapper.py species_notifier "$@"
