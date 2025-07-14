#!/bin/bash

# This script sets up configurations.

cp /app/config_templates/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
mkdir -p /app/config
cp /app/config_templates/birdnet_pi_config.yaml /app/config/birdnet_pi_config.yaml

exit 0
