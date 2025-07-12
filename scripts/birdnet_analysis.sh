#!/usr/bin/env bash

# This script is a wrapper that calls the Python-based analysis manager.
# It is designed to be a drop-in replacement for the original birdnet_analysis.sh script.

# Get the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Call the Python script
python3 "${SCRIPT_DIR}/../src/analysis_manager_wrapper.py" "$@"
