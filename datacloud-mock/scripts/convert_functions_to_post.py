#!/usr/bin/env python3
"""
将 objects_registry.json 中所有 function 的 API 统一为 POST，
path/query 参数迁移至 requestBody。
"""
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_ROOT = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(
    MOCK_ROOT, "mock-resource", "ontology", "crm_demo", "modules", "objects_registry.json"
)


def load_registry() -> dict:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def convert_path(path: str, params: list) -> str:
    """去掉 path 中的 {param}，必要时改为 /update。"""
    for p in params:
        if p.get("in") == "path":
            name = p.get("name", "")
            path = path.replace("{" + name + "}", "")
    # 去掉可能产生的双斜杠
    path = re.sub(r"/+", "/", path).rstrip("/") or "/"
    # 特殊处理：/api/v1/todos 或 /api/v1/expense-reports 需加 /update
    if path == "/api/v1/todos":
        return "/api/v1/todos/update"
    if path == "/api/v1/expense-reports":
        return "/api/v1/expense-reports/update"
    return path


def convert_operation(operation: dict, old_path: str) -> tuple[dict, str]:
    """
    将 operation 转为 POST，parameters 合并到 requestBody。
    返回 (新 operation, 新 path)。
    """
    method = (
        "get"
        if "get" in operation
        else "put"
        if "put" in operation
        else "delete"
        if "delete" in operation
        else "post"
    )
    op = operation.get(method, operation.get("post", {}))
    params = op.get("parameters", [])
    # 已是 POST 且无 path/query 参数，无需转换
    if not params and method == "post":
        return (operation, old_path)
    body = op.get("requestBody", {})
    new_path = convert_path(old_path, params)

    # 构建 requestBody schema
    content = body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get(
        "schema", {"type": "object", "properties": {}, "required": []}
    )
    props = dict(schema.get("properties", {}))
    required = list(schema.get("required", []))

    for p in params:
        if p.get("in") in ("path", "query"):
            name = p.get("name", "")
            props[name] = dict(p.get("schema", {"type": "string"}))
            if "description" in p:
                props[name]["description"] = p["description"]
            if p.get("required", False):
                required.append(name)

    new_schema = {"type": "object", "properties": props}
    if required:
        new_schema["required"] = required

    new_op = {
        "post": {
            "summary": op.get("summary", ""),
            "requestBody": {
                "required": bool(new_schema.get("properties")),
                "content": {"application/json": {"schema": new_schema}},
            },
            "responses": op.get("responses", {"200": {"description": "OK"}}),
        }
    }
    return new_op, new_path


def save_registry(data: dict) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    registry = load_registry()
    for func in registry.get("functions", []):
        schema = func.get("api_schema", {})
        paths = schema.get("paths", {})
        new_paths = {}
        for path, methods in paths.items():
            for method in ("get", "put", "delete", "post"):
                if method in methods:
                    new_op, new_path = convert_operation(methods, path)
                    new_paths[new_path] = new_op
                    break
            else:
                new_paths[path] = methods
        schema["paths"] = new_paths
    save_registry(registry)
    print("Converted objects_registry.json. Run generate_ontology.py to regenerate scenes.")


if __name__ == "__main__":
    main()
