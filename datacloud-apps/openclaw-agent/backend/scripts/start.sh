#!/bin/bash
#
# Start OpenClaw Gateway Service
#

set -e

cd "$(dirname "$0")/.."

# Configuration
HOST="${DATACLOUD_SERVICE_HOST:-0.0.0.0}"
PORT="${DATACLOUD_SERVICE_PORT:-8000}"

# Default API configuration (internal use only)
DEFAULT_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
DEFAULT_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# Use environment variables or defaults (with DATACLOUD_SERVICE_ prefix for config.py)
export DATACLOUD_SERVICE_OPENAI_API_KEY="${DATACLOUD_SERVICE_OPENAI_API_KEY:-$DEFAULT_API_KEY}"
export DATACLOUD_SERVICE_OPENAI_BASE_URL="${DATACLOUD_SERVICE_OPENAI_BASE_URL:-$DEFAULT_BASE_URL}"
# Also export without prefix for openclaw_protocol.py
export OPENAI_API_KEY="${DATACLOUD_SERVICE_OPENAI_API_KEY}"
export OPENAI_BASE_URL="${DATACLOUD_SERVICE_OPENAI_BASE_URL}"

echo "Starting OpenClaw Gateway Service..."
echo "Host: $HOST:$PORT"
echo "API Base: $OPENAI_BASE_URL"

if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  Running in mock mode (no real AI responses)"
else
    echo "✓ Using LLM API"
fi
echo ""

# Start server
exec uv run python -m uvicorn server:app --host "$HOST" --port "$PORT"
