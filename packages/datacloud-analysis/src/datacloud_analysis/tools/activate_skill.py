"""activate_skill tool：LLM 按需激活 skill，读取完整 SKILL.md 并返回处理后内容。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Annotated, Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import DatacloudError
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(
    r"\{\{(query|compute|action|ontology|view|inference|knowledge):([^}]+)\}\}"
)


@tool("activate_skill")
async def activate_skill(
    name: Annotated[str, "要激活的 skill 名称，与 <available_skills> 中的 name 字段完全一致"],
) -> str:
    """按需激活一个 skill，返回其完整指令内容。

    在 <available_skills> 列表中找到匹配的 skill 后调用此工具加载完整指令。
    同一请求内同名 skill 不会重复加载。
    """
    try:
        ctx = get_current_context()
        extras: dict[str, Any] = getattr(ctx, "extras", None) or {}
    except DatacloudError:
        return "[错误] 无法获取请求上下文，activate_skill 失败"

    # 请求级去重（extras dict 在同一请求所有工具调用间共享）
    if "activated_skills" not in extras:
        extras["activated_skills"] = set()
    activated: set[str] = extras["activated_skills"]
    if name in activated:
        logger.info("activate_skill: %r already activated, skipping", name)
        return f"[skill '{name}' 已在本会话中激活，无需重复加载]"

    catalog: list[dict[str, Any]] = extras.get("skill_catalog") or []
    tools_dict: dict[str, Any] = extras.get("tools_dict") or {}

    entry = next((s for s in catalog if s.get("name") == name), None)
    if entry is None:
        available = ", ".join(s.get("name", "") for s in catalog)
        return f"[错误] skill '{name}' 不在可用列表中。可用：{available}"

    body, warnings, err = _load_skill_body(entry["location"], tools_dict)
    if err:
        return err

    activated.add(name)
    logger.info("activate_skill: activated %r (%d chars)", name, len(body))

    result = f"# Skill: {name}\n\n{body}"
    if warnings:
        result += "\n\n" + "\n".join(warnings)
    return result


def _load_skill_body(
    location: str,
    tools_dict: dict[str, Any],
) -> tuple[str, list[str], str]:
    """同步读取 SKILL.md，去掉 frontmatter，执行占位符替换。

    Returns:
        (body, warnings, error_message)  — error_message 非空时表示失败
    """
    skill_md = Path(location)
    if not skill_md.exists():
        return "", [], f"[错误] SKILL.md 文件不存在：{skill_md}"
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        return "", [], f"[错误] 读取 SKILL.md 失败：{exc}"

    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            body = content[end + 4 :].lstrip("\n")

    body, warnings = _replace_placeholders(body, tools_dict)
    return body, warnings, ""


def _replace_placeholders(
    content: str,
    tools_dict: dict[str, Any],
) -> tuple[str, list[str]]:
    """替换占位符：工具类替换为真实 tool 名，本体语义类保留并追加告警。"""
    warnings: list[str] = []

    def replacer(m: re.Match[str]) -> str:
        kind = m.group(1)
        code = m.group(2)

        if kind in ("ontology", "view", "inference", "knowledge"):
            warnings.append(f"⚠️ 本体占位符 {{{{{kind}:{code}}}}} 暂未挂载，由后续本体推理模块填充")
            return m.group(0)

        if kind == "action":
            parts = code.split(":", 1)
            obj_code = parts[0]
            act_name = parts[1] if len(parts) > 1 else ""
            candidates = [k for k in tools_dict if obj_code in k and act_name in k]
            if candidates:
                return candidates[0]
            tool_name = f"{act_name}_{obj_code}" if act_name else obj_code
        else:
            tool_name = f"{kind}_{code}"

        if tool_name not in tools_dict:
            prefixed = f"data_{tool_name}"
            if prefixed in tools_dict:
                return prefixed
            warnings.append(f"⚠️ 工具 {tool_name} 未挂载到当前 agent，无法调用")
            return m.group(0)
        return tool_name

    replaced = _PLACEHOLDER_RE.sub(replacer, content)
    return replaced, warnings
