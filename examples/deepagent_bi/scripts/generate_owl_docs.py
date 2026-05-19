"""从 OWL resource 目录生成 owl_docs/ MD 文件。

用法：
    python scripts/generate_owl_docs.py --resource-dir /path/to/resource --output-dir ./owl_docs
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from datacloud_data_sdk.action import Action
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.virtual_action.generator import (
    build_compute_description,
    build_query_description,
)
from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

logger = logging.getLogger(__name__)


def generate_object_md(obj_code: str, loader: OntologyLoader) -> str:
    """为单个本体对象生成 MD 文档。"""
    cls = loader.get_ontology_class(obj_code)
    lines: list[str] = [
        f"# {cls.object_name}（{obj_code}）",
        "",
        "**类型**：object",
        f"**描述**：{cls.description or ''}",
        "",
    ]

    query_actions = [a for a in cls.actions if getattr(a, "action_family", "") == "query"]
    if query_actions:
        lines += ["## 查询能力（query）", ""]
        lines.append(
            build_query_description(cls.object_name, cls.description or "", cls.fields)
        )
        lines.append("")

    compute_actions = [a for a in cls.actions if getattr(a, "action_family", "") == "compute"]
    if compute_actions:
        lines += ["## 统计能力（compute）", ""]
        lines.append(
            build_compute_description(cls.object_name, cls.description or "", cls.fields)
        )
        lines.append("")

    op_actions = [a for a in cls.actions if getattr(a, "action_family", "") == "operation"]
    if op_actions:
        lines += ["## 操作动作（operations）", ""]
        lines += ["| 动作编码 | 动作名称 | 描述 |", "| --- | --- | --- |"]
        for a in op_actions:
            lines.append(f"| {a.action_code} | {a.action_name} | {a.description or ''} |")
        lines.append("")
        for a in op_actions:
            schema = Action(a, loader).get_schema()
            lines.extend(_format_action_detail(schema))

    return "\n".join(lines)


def generate_view_md(view_code: str, loader: OntologyLoader) -> str:
    """为单个本体视图生成 MD 文档。"""
    view = loader.get_view(view_code)
    view_name = getattr(view, "view_name", view_code)
    view_desc = getattr(view, "description", "")
    fields = list(getattr(view, "fields", []))

    lines: list[str] = [
        f"# {view_name}（{view_code}）",
        "",
        "**类型**：view",
        f"**描述**：{view_desc}",
        "",
    ]

    actions = list(getattr(view, "actions", []))
    query_actions = [a for a in actions if getattr(a, "action_family", "") == "query"]
    if query_actions:
        lines += ["## 查询能力（query）", ""]
        lines.append(build_query_description(view_name, view_desc, fields, scope_type="view"))
        lines.append("")

    compute_actions = [a for a in actions if getattr(a, "action_family", "") == "compute"]
    if compute_actions:
        lines += ["## 统计能力（compute）", ""]
        lines.append(
            build_compute_description(view_name, view_desc, fields, scope_type="view")
        )
        lines.append("")

    return "\n".join(lines)


def _format_action_detail(schema: dict[str, Any]) -> list[str]:
    """将 Action.get_schema() 结果格式化为 MD 详情块。"""
    lines: list[str] = [
        f"### {schema.get('title', schema['name'])}（{schema['name']}）",
        "",
        schema.get("description", ""),
        "",
    ]

    input_schema = schema.get("inputSchema") or {}
    input_props: dict[str, Any] = input_schema.get("properties") or {}
    required: set[str] = set(input_schema.get("required") or [])
    if input_props:
        lines += ["**请求参数**：", "| 参数编码 | 类型 | 必填 | 描述 |", "| --- | --- | --- | --- |"]
        for name, prop in input_props.items():
            lines.append(
                f"| {name} | {prop.get('type', '-')} "
                f"| {'是' if name in required else '否'} "
                f"| {prop.get('description', '')} |"
            )
        lines.append("")

    output_schema = schema.get("outputSchema") or {}
    output_props: dict[str, Any] = output_schema.get("properties") or {}
    if output_props:
        lines += ["**响应字段**：", "| 字段编码 | 类型 | 描述 |", "| --- | --- | --- |"]
        for name, prop in output_props.items():
            lines.append(f"| {name} | {prop.get('type', '-')} | {prop.get('description', '')} |")
        lines.append("")

    return lines


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="从 OWL resource 生成 owl_docs MD 文件")
    parser.add_argument("--resource-dir", required=True, help="OWL resource 根目录")
    parser.add_argument("--output-dir", default="./owl_docs", help="输出目录，默认 ./owl_docs")
    args = parser.parse_args()

    resource_dir = Path(args.resource_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(str(resource_dir))
    inject_virtual_actions(loader)

    obj_codes: list[str] = list(loader._classes.keys())  # type: ignore[attr-defined]
    for obj_code in obj_codes:
        md = generate_object_md(obj_code, loader)
        out_path = output_dir / f"{obj_code}.md"
        out_path.write_text(md, encoding="utf-8")
        logger.info("生成 %s", out_path)

    view_codes: list[str] = list(loader._scenes.keys())  # type: ignore[attr-defined]
    for view_code in view_codes:
        try:
            md = generate_view_md(view_code, loader)
            out_path = output_dir / f"{view_code}.md"
            out_path.write_text(md, encoding="utf-8")
            logger.info("生成 %s", out_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("跳过视图 %s：%s", view_code, exc)

    total = len(list(output_dir.glob("*.md")))
    logger.info("完成，共生成 %d 个文件", total)


if __name__ == "__main__":
    main()
