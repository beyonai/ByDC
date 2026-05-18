"""ontology-manager skill 的 Python Tool 封装。

把 skill 脚本的 main() 逻辑直接封装为 LangChain Tool，
绕开 Windows 下 LocalShellBackend 不支持 bash 的问题。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

_SCRIPTS_DIR = Path(os.environ.get(
    "ONTOLOGY_MANAGER_SKILL_DIR",
    str(Path(__file__).parent.parent / "skills" / "ontology-manager"),
)) / "scripts"


def _run_script(script_name: str, *args: str) -> str:
    """用 subprocess 执行 skill 脚本，捕获 stdout/stderr。"""
    import subprocess  # noqa: PLC0415

    script_path = _SCRIPTS_DIR / script_name
    if not script_path.exists():
        return json.dumps({"ok": False, "error": f"脚本不存在: {script_path}"})

    python = os.environ.get("PYTHON_EXEC", sys.executable)
    result = subprocess.run(
        [python, str(script_path), *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        err = result.stderr.strip()
        if output:
            return output
        return json.dumps({"ok": False, "error": err or f"exit code {result.returncode}"})
    return output if output else json.dumps({"ok": True})


def build_ontology_manager_tools() -> list[Any]:
    """构建 ontology-manager 的所有操作 Tool。"""

    @tool
    def create_ontology_object(object_json: str) -> str:
        """创建本体对象。

        Args:
            object_json: JSON 字符串，包含 entity_name、entity_desc、fields 等字段。
                         支持 --dry-run 前缀预览（如 "--dry-run {...}"）。
        """
        dry_run = object_json.startswith("--dry-run")
        json_str = object_json.replace("--dry-run", "").strip()
        args = ["--dry-run", json_str] if dry_run else [json_str]
        return _run_script("create_object.py", *args)

    @tool
    def modify_ontology_object(object_json: str) -> str:
        """修改本体对象（增减字段、修改关系/动作）。

        Args:
            object_json: JSON 字符串，包含 entity_code 和要修改的字段。
        """
        return _run_script("modify_object.py", object_json)

    @tool
    def delete_ontology_object(resource_id: str, entity_code: str) -> str:
        """删除本体对象。

        Args:
            resource_id: 资源 ID（数字字符串）。
            entity_code: 对象编码（如 by_customer）。
        """
        return _run_script("delete_object.py", resource_id, entity_code)

    @tool
    def create_ontology_view(view_json: str) -> str:
        """创建本体视图。

        Args:
            view_json: JSON 字符串，包含 view_name、view_desc、objects 等字段。
        """
        return _run_script("create_view.py", view_json)

    @tool
    def modify_ontology_view(view_json: str) -> str:
        """修改本体视图。

        Args:
            view_json: JSON 字符串，包含 view_code 和要修改的内容。
        """
        return _run_script("modify_view.py", view_json)

    @tool
    def delete_ontology_view(resource_id: str, view_code: str) -> str:
        """删除本体视图。

        Args:
            resource_id: 资源 ID（数字字符串）。
            view_code: 视图编码。
        """
        return _run_script("delete_view.py", resource_id, view_code)

    @tool
    def list_ontology_resources(resource_type: str = "OBJECT") -> str:
        """查询已有本体列表。

        Args:
            resource_type: 资源类型，"OBJECT" 或 "VIEW"，默认 "OBJECT"。
        """
        return _run_script("list_resources.py", "--type", resource_type.upper())

    @tool
    def get_ontology_detail(resource_id: str) -> str:
        """从 API 获取本体对象或视图的完整详情（实时数据，非本地缓存）。

        Args:
            resource_id: 资源 ID，从 list_ontology_resources 结果中获取。
        """
        return _run_script("get_detail.py", resource_id)

    return [
        create_ontology_object,
        modify_ontology_object,
        delete_ontology_object,
        create_ontology_view,
        modify_ontology_view,
        delete_ontology_view,
        list_ontology_resources,
        get_ontology_detail,
    ]
