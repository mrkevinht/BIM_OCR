#!/bin/sh
set -e

if [ "$RUNPOD_SERVERLESS" = "1" ]; then
    exec python -m worker.serverless
fi

exec uvicorn worker.app:app --host 0.0.0.0 --port 8000
