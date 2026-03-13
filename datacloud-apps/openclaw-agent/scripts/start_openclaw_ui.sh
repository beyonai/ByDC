#!/bin/bash
#
# Start script for datacloud-agent-service with OpenClaw UI
# Starts both the FastAPI server and the OpenClaw UI dev server
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_ROOT/datacloud-apps/datacloud-agent-service"
UI_DIR="$PROJECT_ROOT/ui/openclaw"

# Configuration
SERVICE_HOST="${DATACLOUD_SERVICE_HOST:-0.0.0.0}"
SERVICE_PORT="${DATACLOUD_SERVICE_PORT:-8000}"
UI_PORT="${DATACLOUD_UI_PORT:-3000}"

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down services..."
    
    if [ -n "$SERVICE_PID" ]; then
        kill $SERVICE_PID 2>/dev/null || true
    fi
    if [ -n "$UI_PID" ]; then
        kill $UI_PID 2>/dev/null || true
    fi
    
    echo "Services stopped."
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM

echo "=========================================="
echo "  DataCloud Agent Service + OpenClaw UI"
echo "=========================================="
echo "Service Host: $SERVICE_HOST"
echo "Service Port: $SERVICE_PORT"
echo "UI Port: $UI_PORT"
echo "=========================================="

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed"
    exit 1
fi

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "ERROR: npm is not installed"
    exit 1
fi

# Install UI dependencies if needed
if [ ! -d "$UI_DIR/node_modules" ]; then
    echo "Installing UI dependencies..."
    cd "$UI_DIR"
    npm install
fi

# Start the FastAPI service in background
echo "Starting FastAPI service..."
cd "$SERVICE_DIR"
uv run python -m uvicorn server:app --host "$SERVICE_HOST" --port "$SERVICE_PORT" &
SERVICE_PID=$!

# Wait for service to start
sleep 3

# Check if service started successfully
if ! kill -0 $SERVICE_PID 2>/dev/null; then
    echo "ERROR: Failed to start FastAPI service"
    exit 1
fi

echo "Service started: http://$SERVICE_HOST:$SERVICE_PORT"

# Start the UI in background
echo "Starting OpenClaw UI..."
cd "$UI_DIR"
npm run dev &
UI_PID=$!

# Wait for UI to start
sleep 3

# Check if UI started successfully
if ! kill -0 $UI_PID 2>/dev/null; then
    echo "ERROR: Failed to start UI"
    kill $SERVICE_PID 2>/dev/null || true
    exit 1
fi

echo "UI started: http://localhost:$UI_PORT"
echo ""
echo "=========================================="
echo "  Services Running"
echo "=========================================="
echo "API:  http://$SERVICE_HOST:$SERVICE_PORT/docs"
echo "UI:   http://localhost:$UI_PORT"
echo ""
echo "Press Ctrl+C to stop all services"
echo "=========================================="

# Wait for background processes
wait
