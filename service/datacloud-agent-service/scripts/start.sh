#!/bin/bash
#
# Start script for OpenClaw Gateway Service
# Starts the FastAPI server with configurable host and port
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"

# Change to service directory
cd "$SERVICE_DIR"

# Configuration with defaults
HOST="${DATACLOUD_SERVICE_HOST:-0.0.0.0}"
PORT="${DATACLOUD_SERVICE_PORT:-8000}"
RELOAD="${DATACLOUD_SERVICE_RELOAD:-false}"

echo "=========================================="
echo "  OpenClaw Gateway Service"
echo "=========================================="
echo "Host: $HOST"
echo "Port: $PORT"
echo "Reload: $RELOAD"
echo "=========================================="

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed"
    echo "Please install uv: https://docs.astral.sh/uv/"
    exit 1
fi

# Build command
CMD="uv run python -m uvicorn server:app --host $HOST --port $PORT"

if [ "$RELOAD" = "true" ]; then
    CMD="$CMD --reload"
fi

echo "Starting server..."
echo "API docs: http://$HOST:$PORT/docs"
echo ""

# Run the server
exec $CMD
