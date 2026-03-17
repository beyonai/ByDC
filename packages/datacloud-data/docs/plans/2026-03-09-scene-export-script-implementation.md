# 场景完整 JSON 导出脚本实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 `export_scene_json.py` 脚本，根据场景定义和 objects_registry 生成包含 objects、functions、relations 的完整自包含 JSON。

**Architecture:** 命令行脚本，读取 scene JSON 和 objects_registry JSON，按 object_ids 过滤 objects/relations，从 objects 的 actions 收集 function_refs 过滤 functions，输出合并后的 JSON。

**Tech Stack:** Python 3, argparse, json, pathlib

**Design Doc:** `docs/plans/2026-03-09-scene-export-script-design.md`

---

## Task 1: 编写导出脚本骨架与 CLI

**Files:**
- Create: `datacloud-data/scripts/export_scene_json.py`

**Step 1: 创建脚本文件**

```python
#!/usr/bin/env python3
"""根据场景定义和 objects_registry 生成完整自包含 JSON。

用法:
    python scripts/export_scene_json.py --scene SCENE.json --registry REGISTRY.json --output OUTPUT.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出场景完整 JSON")
    parser.add_argument("--scene", required=True, help="场景 JSON 路径")
    parser.add_argument("--registry", required=True, help="objects_registry.json 路径")
    parser.add_argument("--output", required=True, help="输出 JSON 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scene_path = Path(args.scene)
    registry_path = Path(args.registry)
    output_path = Path(args.output)

    if not scene_path.exists():
        print(f"Error: scene file not found: {scene_path}", file=sys.stderr)
        return 1
    if not registry_path.exists():
        print(f"Error: registry file not found: {registry_path}", file=sys.stderr)
        return 1

    with open(scene_path, encoding="utf-8") as f:
        scene = json.load(f)
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    object_ids = set(scene.get("object_ids", []))
    if not object_ids:
        print("Error: scene has no object_ids", file=sys.stderr)
        return 1

    result = build_scene_json(scene, registry, object_ids)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Exported to {output_path}")
    return 0


def build_scene_json(scene: dict[str, Any], registry: dict[str, Any], object_ids: set[str]) -> dict[str, Any]:
    """构建完整场景 JSON。"""
    # 占位实现
    return {
        "view_id": scene.get("view_id", ""),
        "view_name": scene.get("view_name", ""),
        "description": scene.get("description", ""),
        "functions": [],
        "objects": [],
        "relations": [],
    }


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: 验证脚本可运行**

```bash
cd datacloud-data
python scripts/export_scene_json.py --scene resources/ontology/crm_demo/scene_01_data_analysis.json --registry resources/ontology/crm_demo/objects_registry.json --output /tmp/scene_full.json
```

Expected: 输出 `/tmp/scene_full.json`，内容为 view 元信息 + 空 arrays。

**Step 3: Commit**

```bash
git add scripts/export_scene_json.py
git commit -m "feat: add export_scene_json script skeleton"
```

---

## Task 2: 实现 objects 过滤

**Files:**
- Modify: `datacloud-data/scripts/export_scene_json.py`

**Step 1: 实现 objects 过滤逻辑**

在 `build_scene_json` 中，将占位 `objects` 替换为：

```python
    objects_registry = registry.get("objects", [])
    object_ids_list = scene.get("object_ids", [])  # 保持顺序
    object_by_code = {o["object_code"]: o for o in objects_registry}
    objects = []
    for oid in object_ids_list:
        if oid in object_by_code:
            objects.append(object_by_code[oid])
        else:
            print(f"Warning: object not found in registry: {oid}", file=sys.stderr)
```

需要将 `object_ids` 传入 `build_scene_json`，同时传入 `object_ids_list` 以保持顺序。调整函数签名：

```python
def build_scene_json(
    scene: dict[str, Any],
    registry: dict[str, Any],
    object_ids: set[str],
    object_ids_list: list[str],
) -> dict[str, Any]:
```

在 `main` 中调用时传入：

```python
object_ids_list = scene.get("object_ids", [])
object_ids = set(object_ids_list)
result = build_scene_json(scene, registry, object_ids, object_ids_list)
```

**Step 2: 验证**

```bash
cd datacloud-data
python scripts/export_scene_json.py --scene resources/ontology/crm_demo/scene_01_data_analysis.json --registry resources/ontology/crm_demo/objects_registry.json --output /tmp/scene_full.json
python -c "
import json
with open('/tmp/scene_full.json') as f:
    d = json.load(f)
assert len(d['objects']) == 10
assert [o['object_code'] for o in d['objects']] == ['po_users','po_organization','todo_items','sales_daily_report','sales_business_opportunity','po_users_kpi_detail','sales_customer','po_users_kpi_summary','sales_org_kpi_summary','sales_emp_attendance']
print('OK')
"
```

**Step 3: Commit**

```bash
git add scripts/export_scene_json.py
git commit -m "feat: filter objects by object_ids"
```

---

## Task 3: 实现 relations 过滤

**Files:**
- Modify: `datacloud-data/scripts/export_scene_json.py`

**Step 1: 在 build_scene_json 中添加 relations 过滤**

```python
    relations_registry = registry.get("relations", [])
    relations = [
        r for r in relations_registry
        if r.get("source_class") in object_ids and r.get("target_class") in object_ids
    ]
```

将 `relations` 加入返回的 dict。

**Step 2: 验证**

```bash
cd datacloud-data
python scripts/export_scene_json.py --scene resources/ontology/crm_demo/scene_01_data_analysis.json --registry resources/ontology/crm_demo/objects_registry.json --output /tmp/scene_full.json
python -c "
import json
with open('/tmp/scene_full.json') as f:
    d = json.load(f)
assert len(d['relations']) > 0
for r in d['relations']:
    assert r['source_class'] in ['po_users','po_organization','todo_items','sales_daily_report','sales_business_opportunity','po_users_kpi_detail','sales_customer','po_users_kpi_summary','sales_org_kpi_summary','sales_emp_attendance']
    assert r['target_class'] in ['po_users','po_organization','todo_items','sales_daily_report','sales_business_opportunity','po_users_kpi_detail','sales_customer','po_users_kpi_summary','sales_org_kpi_summary','sales_emp_attendance']
print('OK')
"
```

**Step 3: Commit**

```bash
git add scripts/export_scene_json.py
git commit -m "feat: filter relations by object_ids"
```

---

## Task 4: 实现 functions 过滤

**Files:**
- Modify: `datacloud-data/scripts/export_scene_json.py`

**Step 1: 收集 function_refs 并过滤 functions**

在 `build_scene_json` 中，从过滤后的 `objects` 收集所有 `function_refs`：

```python
    function_codes: set[str] = set()
    for obj in objects:
        for action in obj.get("actions", []):
            for fc in action.get("function_refs", []):
                function_codes.add(fc)

    functions_registry = registry.get("functions", [])
    func_by_code = {f["function_code"]: f for f in functions_registry}
    functions = [func_by_code[fc] for fc in function_codes if fc in func_by_code]
```

将 `functions` 加入返回的 dict。

**Step 2: 验证**

```bash
cd datacloud-data
python scripts/export_scene_json.py --scene resources/ontology/crm_demo/scene_01_data_analysis.json --registry resources/ontology/crm_demo/objects_registry.json --output /tmp/scene_full.json
python -c "
import json
with open('/tmp/scene_full.json') as f:
    d = json.load(f)
assert len(d['functions']) > 0
fc_set = {f['function_code'] for f in d['functions']}
# 至少应有 todo/po 相关函数
assert 'fn_todo_query_list' in fc_set or 'fn_po_users_query_by_ids' in fc_set
print('OK')
"
```

**Step 3: Commit**

```bash
git add scripts/export_scene_json.py
git commit -m "feat: filter functions by object action refs"
```

---

## Task 5: 添加单元测试

**Files:**
- Create: `datacloud-data/tests/scripts/test_export_scene_json.py`

**Step 1: 编写测试**

```python
"""测试 export_scene_json 脚本。"""

import json
from pathlib import Path

import pytest

# 假设脚本在 scripts/ 下，项目根为 datacloud-data
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = PROJECT_ROOT / "resources/ontology/crm_demo/scene_01_data_analysis.json"
REGISTRY_PATH = PROJECT_ROOT / "resources/ontology/crm_demo/objects_registry.json"


def test_build_scene_json():
    from scripts.export_scene_json import build_scene_json

    with open(SCENE_PATH, encoding="utf-8") as f:
        scene = json.load(f)
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)

    object_ids_list = scene.get("object_ids", [])
    object_ids = set(object_ids_list)
    result = build_scene_json(scene, registry, object_ids, object_ids_list)

    assert result["view_id"] == "scene_01_data_analysis"
    assert result["view_name"] == "在线查数分析场景"
    assert len(result["objects"]) == 10
    assert len(result["relations"]) > 0
    assert len(result["functions"]) > 0

    obj_codes = {o["object_code"] for o in result["objects"]}
    assert obj_codes == set(object_ids_list)

    for r in result["relations"]:
        assert r["source_class"] in object_ids
        assert r["target_class"] in object_ids
```

注意：若项目结构不支持 `from scripts.export_scene_json import`，可改为 subprocess 调用脚本并检查输出文件。

**Step 2: 若 import 失败，改用 subprocess 测试**

```python
"""测试 export_scene_json 脚本。"""

import json
import subprocess
from pathlib import Path

import pytest

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
            "--scene", str(SCENE_PATH),
            "--registry", str(REGISTRY_PATH),
            "--output", str(out),
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
    assert len(result["objects"]) == 10
    assert len(result["relations"]) > 0
    assert len(result["functions"]) > 0

    object_ids = {"po_users", "po_organization", "todo_items", "sales_daily_report",
                  "sales_business_opportunity", "po_users_kpi_detail", "sales_customer",
                  "po_users_kpi_summary", "sales_org_kpi_summary", "sales_emp_attendance"}
    obj_codes = {o["object_code"] for o in result["objects"]}
    assert obj_codes == object_ids

    for r in result["relations"]:
        assert r["source_class"] in object_ids
        assert r["target_class"] in object_ids
```

**Step 3: 运行测试**

```bash
cd datacloud-data
pytest tests/scripts/test_export_scene_json.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add tests/scripts/test_export_scene_json.py
git commit -m "test: add export_scene_json tests"
```

---

## Task 6: 生成示例输出并更新 README（可选）

**Files:**
- Create: `datacloud-data/resources/ontology/crm_demo/scene_01_data_analysis_full.json`（通过运行脚本生成）
- Modify: `datacloud-data/README.md`（若有 scripts 说明则补充）

**Step 1: 运行脚本生成 full JSON**

```bash
cd datacloud-data
python scripts/export_scene_json.py \
  --scene resources/ontology/crm_demo/scene_01_data_analysis.json \
  --registry resources/ontology/crm_demo/objects_registry.json \
  --output resources/ontology/crm_demo/scene_01_data_analysis_full.json
```

**Step 2: 若 README 有 scripts 章节，补充说明**

在 README 的 scripts 或开发说明中增加：

```markdown
### 导出场景完整 JSON

根据场景定义和 objects_registry 生成自包含的完整 JSON：

    python scripts/export_scene_json.py \
      --scene resources/ontology/crm_demo/scene_01_data_analysis.json \
      --registry resources/ontology/crm_demo/objects_registry.json \
      --output resources/ontology/crm_demo/scene_01_data_analysis_full.json
```

**Step 3: Commit**

```bash
git add resources/ontology/crm_demo/scene_01_data_analysis_full.json
# 若修改了 README
git add README.md
git commit -m "chore: add scene_01_data_analysis_full.json and script docs"
```

---

## 执行选项

计划已保存到 `docs/plans/2026-03-09-scene-export-script-implementation.md`。两种执行方式：

1. **Subagent-Driven（本会话）**：按任务逐个派发子 agent，任务间做代码审查，快速迭代。
2. **Parallel Session（独立会话）**：在新会话中用 executing-plans，按检查点批量执行。

你希望用哪种方式？
