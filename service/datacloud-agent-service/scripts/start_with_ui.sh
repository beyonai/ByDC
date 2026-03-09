#!/bin/bash
#
# Start script for OpenClaw Gateway Service with UI
# Starts both the FastAPI server and the Next.js UI dev server
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SERVICE_DIR")")"
UI_DIR="$PROJECT_ROOT/ui/deep-agents-ui"

# Configuration
SERVICE_HOST="${DATACLOUD_SERVICE_HOST:-0.0.0.0}"
SERVICE_PORT="${DATACLOUD_SERVICE_PORT:-8000}"
UI_PORT="${DATACLOUD_UI_PORT:-3000}"

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down services..."
    
    # Kill background jobs
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
echo "  OpenClaw Gateway Service + UI"
echo "=========================================="
echo "Service Host: $SERVICE_HOST"
echo "Service Port: $SERVICE_PORT"
echo "UI Port: $UI_PORT"
echo "=========================================="

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed"
    echo "Please install uv: https://docs.astral.sh/uv/"
    exit 1
fi

# Start the FastAPI service in background
echo "Starting FastAPI service..."
cd "$SERVICE_DIR"
uv run python -m uvicorn server:app --host "$SERVICE_HOST" --port "$SERVICE_PORT" &
SERVICE_PID=$!

# Wait a moment for service to start
sleep 2

# Check if service started successfully
if ! kill -0 $SERVICE_PID 2>/dev/null; then
    echo "ERROR: Failed to start FastAPI service"
    exit 1
fi

echo "Service started: http://$SERVICE_HOST:$SERVICE_PORT/docs"

# Check if yarn is available
if ! command -v yarn &> /dev/null && ! command -v npm &> /dev/null; then
    echo "ERROR: Neither yarn nor npm is installed"
    echo "Please install Node.js and yarn/npm"
    kill $SERVICE_PID 2>/dev/null || true
    exit 1
fi

# Start the UI in background
echo "Starting UI dev server..."
cd "$UI_DIR"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing UI dependencies..."
    if command -v yarn &> /dev/null; then
        yarn install
    else
        npm install
    fi
fi

# Start UI dev server
if command -v yarn &> /dev/null; then
    PORT=$UI_PORT yarn dev &
    UI_PID=$!
else
    PORT=$UI_PORT npm run dev &
    UI_PID=$!
fi

# Wait a moment for UI to start
sleep 3

# Check if UI started successfully
if ! kill -0 $UI_PID 2>/dev/null; then
    echo "ERROR: Failed to start UI dev server"
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
