#!/usr/bin/env bash
set -a
# shellcheck source=.demo_env
source "$(dirname "$0")/.demo_env"
set +a

cd "$(dirname "$0")"
exec uv run python demo_normal.py
