#!/bin/bash

# Start Caddy in the background
caddy run --config /etc/caddy/Caddyfile &

# Start the FastAPI application
uv run uvicorn src.web.main:app --host 0.0.0.0 --port 8000 > /var/log/fastapi.log 2>&1 &
sleep 10
