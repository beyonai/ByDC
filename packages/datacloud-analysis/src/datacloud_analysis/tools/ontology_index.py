"""本体对象 AOCI 格式索引生成器。

AOCI（AI-Oriented Code Indexing）思想：
  把低熵原始内容（完整工具 schema，每个 ~500 token）
  压缩为高熵结构化摘要（坐标 + 语义，每个 ~30-80 token）
  按重要性分配 token 预算，注入 L1 system prompt 常驻缓存层。

索引格式（每行一个对象）：
  object_code[importance]: F:<业务角色> | R:<关联对象> | A:<动作列表> | S:<高熵解锁说明>

  F  业务角色    —— entity_desc 的精炼版，一句话
  R  关联对象    —— object_relations 中的 target_code 列表
  A  动作列表    —— 暴露的 action_code 列表
  S  高熵说明    —— unlock_reason（无法从名称推断的推理跳转逻辑）

token 预算策略（参考 AOCI 重要性分层）：
  importance=9  核心诊断入口对象    80-120 token/条
  importance=7  关键配置/知识对象   50-80  token/条
  importance=5  辅助/扩展对象       20-40  token/条

压缩效果：
  20个 ops_* 对象的完整工具 schema ≈ 10,000-20,000 token
  同等信息的 AOCI 索引              ≈ 800-1,500  token
  压缩比约 1:10 ~ 1:15，且保留全部推理所需语义
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 重要性分层规则（object_code 关键词 → 重要性数字）
_IMPORTANCE_RULES: list[tuple[list[str], str]] = [
    # 核心诊断入口：每次推理必经，最高优先级
    (["langfuse_trace", "early_span"], "9"),
    # 关键工具对象：诊断链路核心节点
    (["tool_call_span", "llm_gen_span", "graph_node_span"], "8"),
    # 配置类对象：故障根因定位必需
    (["llm_config", "dig_employee", "datacloud_config", "db_config"], "7"),
    # 知识库对象：故障经验检索
    (["fault_config", "fault_ontology", "fault_term", "fault_analytics", "fault_service"], "7"),
    # OWL 元数据对象：本体诊断使用
    (["owl_object", "owl_action", "owl_dbsource"], "6"),
    # 术语对象
    (["term_relation", "term_knowledge", "term_name", "term_type"], "5"),
    # 日志/运营分析对象
    (["app_log", "error_log", "agent_trace", "eval_score"], "5"),
]

# 每个重要性级别的字段长度上限（字符数）
_BUDGET: dict[str, dict[str, int]] = {
    "9": {"f": 80, "r": 120, "a": 80, "s": 150},
    "8": {"f": 60, "r": 100, "a": 60, "s": 120},
    "7": {"f": 50, "r": 80,  "a": 50, "s": 100},
    "6": {"f": 40, "r": 60,  "a": 40, "s": 60},
    "5": {"f": 30, "r": 40,  "a": 30, "s": 40},
}


def _infer_importance(object_code: str) -> str:
    """根据 object_code 中的关键词推断重要性级别。"""
    for keywords, importance in _IMPORTANCE_RULES:
        if any(kw in object_code for kw in keywords):
            return importance
    return "5"


def _truncate(text: str, max_chars: int) -> str:
    """截断文本，超长时加省略号。"""
    if not text:
        return "-"
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _extract_entity_desc(obj: Any) -> str:
    """从 OWL 对象提取描述字段，尝试多个属性名。"""
    for attr in ("entity_desc", "description", "entity_name", "object_name"):
        val = getattr(obj, attr, None)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_action_codes(obj: Any) -> list[str]:
    """从 OWL 对象提取所有 action_code 列表。"""
    codes: list[str] = []
    try:
        actions = getattr(obj, "actions", None) or []
        for a in actions:
            code = getattr(a, "action_code", None) or getattr(a, "name", None)
            if code:
                codes.append(str(code))
    except Exception:
        pass
    return codes


def build_ontology_index(loader: Any, object_codes: list[str]) -> str:
    """把 OWL 对象列表压缩为 AOCI 格式本体索引字符串。

    Args:
        loader:       已初始化的 OntologyLoader 实例（含 _classes + relations）
        object_codes: 需要索引的对象 code 列表

    Returns:
        多行字符串，每行一个对象条目 + 头部说明。
        为空列表时返回空字符串。
    """
    if not object_codes:
        return ""

    # ── 1. 预处理：建立 object_code → 关系列表 映射 ──────────────────────────
    relation_map: dict[str, list[dict[str, str]]] = {}
    try:
        for rel in loader.get_ontology_relations():
            src: str = getattr(rel, "source_class", "") or ""
            if not src:
                continue
            # 提取 resolve_action_code（可能在 description JSON 里）
            action_code: str = (
                getattr(rel, "resolve_action_code", None)
                or getattr(rel, "relation_name", None)
                or ""
            )
            # 从 description JSON 补充 unlock_reason
            unlock_reason = ""
            desc_raw = getattr(rel, "description", "") or ""
            if desc_raw:
                try:
                    meta = json.loads(desc_raw)
                    action_code = action_code or meta.get("resolve_action_code", "")
                    unlock_reason = meta.get("unlock_reason", "")
                except (json.JSONDecodeError, TypeError):
                    unlock_reason = desc_raw[:60]

            if not action_code:
                continue  # 没有 resolve_action_code 的关系不参与索引

            target: str = getattr(rel, "target_class", "") or ""
            if src not in relation_map:
                relation_map[src] = []
            relation_map[src].append({
                "target": target,
                "action": action_code,
                "reason": unlock_reason,
            })
    except Exception:
        logger.debug("OntologyIndex: failed to load relations", exc_info=True)

    # ── 2. 按重要性分组排序（高重要性在前）────────────────────────────────────
    scored: list[tuple[int, str]] = []
    for code in object_codes:
        imp = _infer_importance(code)
        scored.append((int(imp), code))
    scored.sort(key=lambda x: x[0], reverse=True)

    # ── 3. 逐对象生成索引条目 ──────────────────────────────────────────────────
    entries: list[str] = []
    for importance_int, code in scored:
        importance = str(importance_int)
        budget = _BUDGET.get(importance, _BUDGET["5"])

        # 尝试从 loader 获取对象定义
        obj = None
        try:
            obj = loader.get_ontology_class(code)
        except Exception:
            pass

        # F: 业务角色
        if obj is not None:
            raw_desc = _extract_entity_desc(obj)
        else:
            raw_desc = code.replace("_", " ")
        f_field = _truncate(raw_desc, budget["f"])

        # R: 关联对象（取 target 列表，按 budget 截断）
        rels = relation_map.get(code, [])
        if rels:
            targets = [r["target"] for r in rels]
            r_str = ",".join(targets)
            r_field = _truncate(r_str, budget["r"])
        else:
            r_field = "-"

        # A: 动作列表
        if obj is not None:
            action_codes = _extract_action_codes(obj)
        else:
            # 从 TOOL_TO_OBJECT 反查（工具已注册时）
            try:
                from datacloud_analysis.tools.tool_pool import TOOL_TO_OBJECT  # noqa: PLC0415
                action_codes = [t for t, oc in TOOL_TO_OBJECT.items() if oc == code]
            except Exception:
                action_codes = []
        a_str = ",".join(action_codes) if action_codes else "-"
        a_field = _truncate(a_str, budget["a"])

        # S: 高熵解锁说明（最有推理价值：告诉 LLM 调这个对象的工具后会发生什么）
        if rels:
            s_parts = []
            remaining = budget["s"]
            for r in rels:
                if not r["reason"]:
                    continue
                fragment = f"{r['action']}→{r['reason']}"
                if len(fragment) + 2 > remaining:
                    fragment = fragment[: remaining - 1] + "…"
                    s_parts.append(fragment)
                    break
                s_parts.append(fragment)
                remaining -= len(fragment) + 2
                if remaining <= 0:
                    break
            s_field = "; ".join(s_parts) if s_parts else "-"
        else:
            s_field = "-"

        entries.append(
            f"{code}[{importance}]: F:{f_field} | R:{r_field} | A:{a_field} | S:{s_field}"
        )

    if not entries:
        return ""

    header = (
        "## 本体对象索引\n"
        "# 格式：object_code[重要性9-5]: F:业务角色 | R:关联对象 | A:动作列表 | S:解锁后跳转说明\n"
        "# 推理入口从重要性9的对象开始；S字段说明调用该对象工具后after_hook会解锁哪些下一跳\n"
    )
    return header + "\n".join(entries)
