#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env_deepagent"
MOCK_DIR="$(cd "$SCRIPT_DIR/../../../whale_datacloud_mock/mock_services" 2>/dev/null || echo "")"

# ── 加载环境变量 ──────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    echo "错误：未找到 $ENV_FILE，请先复制模板并填写配置" >&2
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

# ── 解析参数 ──────────────────────────────────────────────────────────────────
SYNC_OWL=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --sync-owl) SYNC_OWL=true; shift ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

# ── 启动 mock_services ────────────────────────────────────────────────────────
BYAI_PID=""
SQLITE_PID=""
PROXY_PID=""

if [[ -n "$MOCK_DIR" && -d "$MOCK_DIR" ]]; then
    echo ">>> 启动 mock_services..."
    cd "$MOCK_DIR"
    uv run uvicorn byai_api.main:app --host 0.0.0.0 --port 8080 &
    BYAI_PID=$!
    uv run uvicorn sqlite_api.main:app --host 0.0.0.0 --port 51919 &
    SQLITE_PID=$!
    sleep 2
    echo ">>> mock_services 已启动 (byai_api pid=$BYAI_PID, sqlite_api pid=$SQLITE_PID)"
else
    echo ">>> 未找到 mock_services 目录，跳过启动（请确保依赖服务已在运行）"
fi

# ── 清理函数 ──────────────────────────────────────────────────────────────────
cleanup() {
    echo ">>> 停止后台服务..."
    [[ -n "$BYAI_PID" ]] && kill "$BYAI_PID" 2>/dev/null || true
    [[ -n "$SQLITE_PID" ]] && kill "$SQLITE_PID" 2>/dev/null || true
    [[ -n "$PROXY_PID" ]] && kill "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── 可选：同步生成 owl_docs ───────────────────────────────────────────────────
if [[ "$SYNC_OWL" == "true" ]]; then
    if [[ -z "${OWL_RESOURCE_DIR:-}" ]]; then
        echo "错误：--sync-owl 需要在 .env_deepagent 中设置 OWL_RESOURCE_DIR" >&2
        exit 1
    fi
    echo ">>> 生成 owl_docs（resource-dir=$OWL_RESOURCE_DIR）..."
    cd "$SCRIPT_DIR"
    uv run python scripts/generate_owl_docs.py \
        --resource-dir "$OWL_RESOURCE_DIR" \
        --output-dir "$SCRIPT_DIR/owl_docs"
    echo ">>> owl_docs 生成完成"
fi

# ── 启动前端代理（前端 + API 反向代理，合并到同一端口）────────────────────────
echo ">>> 启动前端代理（http://localhost:8765/app/）..."
cd "$SCRIPT_DIR"
python -m uvicorn proxy:app --port 8765 &
PROXY_PID=$!
sleep 2
echo ">>> 前端代理已启动 (pid=$PROXY_PID)"

# ── 启动 DeepAgent API ────────────────────────────────────────────────────────
echo ""
echo ">>> 对话界面：http://localhost:8765/app/"
echo ">>> DeepAgent API：http://localhost:2026"
echo ""
cd "$SCRIPT_DIR"
source "$SCRIPT_DIR/.venv-wsl/bin/activate"
exec langgraph dev --allow-blocking --no-browser --no-reload --port 2026
