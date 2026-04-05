"""测试 export_scene_json 脚本。"""

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = PROJECT_ROOT / "resources/ontology/crm_demo/scene_01_data_analysis.json"
REGISTRY_PATH = PROJECT_ROOT / "resources/ontology/crm_demo/objects_registry.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts/export_scene_json.py"


def test_export_scene_json_produces_valid_output(tmp_path):
    out = tmp_path / "scene_full.json"
    r = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--scene",
            str(SCENE_PATH),
            "--registry",
            str(REGISTRY_PATH),
            "--output",
            str(out),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    with open(out, encoding="utf-8") as f:
        result = json.load(f)

    assert result["view_id"] == "scene_01_data_analysis"
    assert result["view_name"] == "在线查数分析场景"
    assert len(result["objects"]) > 0
    assert len(result["relations"]) > 0
    assert len(result["functions"]) > 0

    # 原始 10 个核心对象必须存在
    core_object_ids = {
        "po_users",
        "po_organization",
        "todo_items",
        "sales_daily_report",
        "sales_business_opportunity",
        "po_users_kpi_detail",
        "sales_customer",
        "po_users_kpi_summary",
        "sales_org_kpi_summary",
        "sales_emp_attendance",
    }
    obj_codes = {o["object_code"] for o in result["objects"]}
    assert core_object_ids.issubset(obj_codes)

    for rel in result["relations"]:
        assert rel["source_class"] in obj_codes
        assert rel["target_class"] in obj_codes
