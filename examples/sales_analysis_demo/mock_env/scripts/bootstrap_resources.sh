#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${ROOT_DIR}/data_tools"

echo "[bootstrap] root: ${ROOT_DIR}"
echo "[bootstrap] refresh CRM data resources"
python "${TOOLS_DIR}/fix_and_generate_crm_data.py"
python "${TOOLS_DIR}/gen_attendance.py"
python "${TOOLS_DIR}/gen_kpi_completion.py"

echo "[bootstrap] refresh ontology resources"
python "${TOOLS_DIR}/convert_functions_to_post.py"
python "${TOOLS_DIR}/fix_camel_and_params.py"
python "${TOOLS_DIR}/generate_ontology.py"

echo "[bootstrap] done"
