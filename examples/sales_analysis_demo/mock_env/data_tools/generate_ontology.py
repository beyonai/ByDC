#!/usr/bin/env python3
"""
生成各销售场景的本地对象 JSON 文件。
从 objects_registry.json 共享库中，按场景声明的对象编码裁剪，
输出4个自包含的 OBJECT 级场景 JSON 文件。
"""

import json
import os
from datetime import datetime, timezone

# ===== 场景配置 =====
SCENE_CONFIGS = {
    "scene_01_data_analysis": {
        "metadata_name": "在线查数分析场景",
        "description": "销售数据分析场景，支持简单查询、跨库联合检索、非结构化融合检索",
        "object_codes": [
            "po_users",
            "po_organization",
            "sales_business_opportunity",
            "po_users_kpi_summary",
            "po_users_kpi_detail",
            "sales_org_kpi_summary",
            "sales_customer",
            "sales_emp_attendance",
            "todo_items",
            "sales_daily_report",
        ],
    },
    "scene_02_behavior_mgmt": {
        "metadata_name": "销售行为管理场景",
        "description": "面向销售员工与主管的行为管理，打卡、待办、费用、会议纪要、日报一体化",
        "object_codes": [
            "po_users",
            "sales_emp_attendance",
            "todo_items",
            "sales_expense_report",
            "sales_business_opportunity",
            "sales_customer",
            "sales_meeting_note",
            "sales_daily_report",
        ],
    },
    "scene_03_insight_analysis": {
        "metadata_name": "销售洞察分析场景",
        "description": "人员立体画像与商机对赌分析，整合结构化与非结构化多源数据",
        "object_codes": [
            "po_users",
            "po_organization",
            "po_users_kpi_summary",
            "po_users_kpi_completion",
            "po_users_kpi_detail",
            "sales_org_kpi_summary",
            "sales_org_kpi_completion",
            "sales_business_opportunity",
            "sales_customer",
            "sales_expense_report",
            "sales_emp_attendance",
            "sales_daily_report",
            "sales_meeting_note",
            "todo_items",
        ],
    },
    "scene_04_decision_deduction": {
        "metadata_name": "销售决策推演场景",
        "description": "针对管理政策效果分析与突发事件应对的决策推演",
        "object_codes": [
            "po_users",
            "po_organization",
            "sales_business_opportunity",
            "sales_customer",
            "po_users_kpi_detail",
            "sales_emp_attendance",
            "sales_daily_report",
            "todo_items",
        ],
    },
}


def load_registry(registry_path: str) -> dict:
    with open(registry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_scene(registry: dict, scene_key: str, scene_config: dict) -> dict:
    object_codes = set(scene_config["object_codes"])

    # 过滤 objects（保留完整属性和动作）
    scene_objects = [o for o in registry["objects"] if o["object_code"] in object_codes]

    # 收集场景内 objects 动作引用的所有 function_codes
    needed_function_codes: set[str] = set()
    for obj in scene_objects:
        for action in obj.get("actions", []):
            for fref in action.get("function_refs", []):
                needed_function_codes.add(fref)
            if "function_ref" in action:
                needed_function_codes.add(action["function_ref"])

    # 过滤 functions（只包含被引用的）
    scene_functions = [
        f for f in registry["functions"] if f["function_code"] in needed_function_codes
    ]

    # 过滤 relations（source 和 target 都在场景内）
    scene_relations = [
        r
        for r in registry["relations"]
        if r["source_object_ref"] in object_codes and r["target_object_ref"] in object_codes
    ]

    return {
        "$schema": "https://datacloud.io/schemas/ontology/v1.0",
        "version": "1.0",
        "scope": "OBJECT",
        "metadata": {
            "name": scene_config["metadata_name"],
            "description": scene_config["description"],
            "author": "admin",
            "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tenant_id": "TENANT_001",
            "domain_ref": "sales",
        },
        "functions": scene_functions,
        "objects": scene_objects,
        "relations": scene_relations,
    }


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mock_root = os.path.dirname(script_dir)
    modules_dir = os.path.join(
        mock_root, "resource", "knowledge", "crm_demo", "ontology", "modules"
    )
    registry_path = os.path.join(modules_dir, "objects_registry.json")

    print(f"Loading registry from: {registry_path}")
    registry = load_registry(registry_path)
    print(
        f"Registry loaded: {len(registry['objects'])} objects, "
        f"{len(registry['functions'])} functions, "
        f"{len(registry['relations'])} relations"
    )
    print()

    for scene_key, scene_config in SCENE_CONFIGS.items():
        scene_data = extract_scene(registry, scene_key, scene_config)
        output_path = os.path.join(modules_dir, f"{scene_key}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(scene_data, f, ensure_ascii=False, indent=2)
        print(
            f"Generated: {scene_key}.json  "
            f"({len(scene_data['objects'])} objects, "
            f"{len(scene_data['functions'])} functions, "
            f"{len(scene_data['relations'])} relations)"
        )

    print("\nDone!")


if __name__ == "__main__":
    main()
