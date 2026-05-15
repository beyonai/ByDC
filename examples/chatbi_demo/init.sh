#!/usr/bin/env bash
set -euo pipefail
set -a
# shellcheck source=.demo_env
source "$(dirname "$0")/.demo_env"
set +a

cd "$(dirname "$0")"
exec uv run python init.py
