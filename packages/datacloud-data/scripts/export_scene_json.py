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

    object_ids_list = scene.get("object_ids", [])
    object_ids = set(object_ids_list)
    if not object_ids:
        print("Error: scene has no object_ids", file=sys.stderr)
        return 1

    result = build_scene_json(scene, registry, object_ids, object_ids_list)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Exported to {output_path}")
    return 0


def build_scene_json(
    scene: dict[str, Any],
    registry: dict[str, Any],
    object_ids: set[str],
    object_ids_list: list[str],
) -> dict[str, Any]:
    """构建完整场景 JSON。"""
    objects_registry = registry.get("objects", [])
    object_by_code = {o["object_code"]: o for o in objects_registry}
    objects = []
    for oid in object_ids_list:
        if oid in object_by_code:
            objects.append(object_by_code[oid])
        else:
            print(f"Warning: object not found in registry: {oid}", file=sys.stderr)

    relations_registry = registry.get("relations", [])
    relations = [
        r
        for r in relations_registry
        if r.get("source_class") in object_ids and r.get("target_class") in object_ids
    ]

    function_codes: set[str] = set()
    for obj in objects:
        for action in obj.get("actions", []):
            for fc in action.get("function_refs", []):
                function_codes.add(fc)

    functions_registry = registry.get("functions", [])
    func_by_code = {f["function_code"]: f for f in functions_registry}
    functions = [func_by_code[fc] for fc in function_codes if fc in func_by_code]

    return {
        "view_id": scene.get("view_id", ""),
        "view_name": scene.get("view_name", ""),
        "description": scene.get("description", ""),
        "functions": functions,
        "objects": objects,
        "relations": relations,
    }


if __name__ == "__main__":
    sys.exit(main())
