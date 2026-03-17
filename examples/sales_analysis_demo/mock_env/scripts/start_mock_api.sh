#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[start] sales-analysis-demo on ${HOST}:${PORT}"
uvicorn sales_analysis_demo.main:app --host "${HOST}" --port "${PORT}"
