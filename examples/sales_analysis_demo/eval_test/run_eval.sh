#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${SCRIPT_DIR}/cases"
REPORT_DIR="${SCRIPT_DIR}/reports"
BASELINE_DIR="${SCRIPT_DIR}/baselines"
OUTPUT="${REPORT_DIR}/latest.json"

mkdir -p "${REPORT_DIR}" "${BASELINE_DIR}"

echo "[eval] cases dir: ${CASE_DIR}"
echo "[eval] output: ${OUTPUT}"
echo "[eval] TODO: replace with real eval runner"

cat > "${OUTPUT}" <<EOF
{
  "status": "placeholder",
  "message": "run_eval.sh scaffold is ready",
  "cases_dir": "${CASE_DIR}",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

echo "[eval] done"
