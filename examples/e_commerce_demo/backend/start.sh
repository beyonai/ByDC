#!/usr/bin/env bash
# DataCloud Service — 启动脚本（Linux / macOS）
#
# 用法：
#   bash examples/e_commerce_demo/backend/start.sh          # 从仓库根目录
#   bash start.sh                                            # 从 backend/ 目录
#
set -euo pipefail

# 定位到仓库根目录（whale_datacloud/）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "▶  Working directory: ${REPO_ROOT}"
cd "${REPO_ROOT}"

# 确保依赖已同步（首次运行或 pyproject.toml 变更后需要）
# uv sync --group dev

exec uv run python examples/e_commerce_demo/backend/datacloud_service/main.py "$@"
