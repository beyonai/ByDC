#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env_deepagent"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "错误：未找到 $ENV_FILE" >&2
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

source "$SCRIPT_DIR/.venv-wsl/bin/activate"

echo ">>> 启动 DeepAgent API（http://127.0.0.1:2026）..."
echo ">>> 对话界面：http://localhost:8765/app/"
exec langgraph dev --allow-blocking --no-browser --no-reload --port 2026
