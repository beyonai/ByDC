#!/bin/bash
#
# Start OpenClaw UI dev server
#

set -e

cd "$(dirname "$0")/.."

PORT="${OPENCLAW_UI_PORT:-3000}"

echo "Starting OpenClaw UI..."
echo "Port: $PORT"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start dev server
exec npm run dev -- --port "$PORT"
