"""召回共享常量和工具函数 — 消除 typed_recall ↔ batch_recall 循环依赖。

本模块为 typed_recall.py 和 batch_recall.py 提供共享的类型定义、常量映射和
候选整形函数。两个模块均可从本模块导入，不产生循环依赖。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ── 类型别名 ──────────────────────────────────────────────────

CandidateDict = dict[str, Any]

# ── ktype → 允许的 type_category 集合 ──────────────────────────
# type_category 定义（term_type 表）:
#   1 = 列表术语 (LIST_TERM)    — 企业名、地址、网格名等维度值
#   2 = 字典术语 (DICT_TERM)    — 行业、状态、等级等枚举值
#   3 = 本体术语 (ONTOLOGY_TERM) — object/view/action/prop 等结构定义
#
# whereValue 需要匹配具体的值（列表/字典术语）
# select/groupBy/whereKey/orderBy 需要匹配字段/对象（本体术语）
# aggregation 不走知识召回

KTYPE_CATEGORY_MAP: Final[dict[str, set[int] | None]] = {
    "select": {3},
    "groupBy": {3},
    "whereKey": {3},
    "whereValue": {1, 2},
    "orderBy": {3},
    "aggregation": None,
}

# whereValue 单路多样性：每个 term_type_code 最多保留几条
_WHERE_VALUE_PER_TYPE: Final[int] = 3


def _diversify_by_type(
    ranked: list[tuple[str, str, str, str, str]],
    per_type: int = _WHERE_VALUE_PER_TYPE,
) -> list[tuple[str, str, str, str, str]]:
    """按 term_type_code 分组截断，保证类型多样性。

    输入 tuple: (term_id, term_name, name_id, term_type_code, term_code)。
    保持原始排序，每个 type 最多保留 per_type 条。
    """
    type_counts: dict[str, int] = defaultdict(int)
    result: list[tuple[str, str, str, str, str]] = []
    for item in ranked:
        ttc = item[3]  # term_type_code
        if type_counts[ttc] < per_type:
            result.append(item)
            type_counts[ttc] += 1
    return result


def _load_type_codes_by_category(
    session: Session,
    categories: set[int],
) -> set[str]:
    """从 term_type 表按 type_category 加载 type_code 集合。"""
    from datacloud_knowledge.db.models import TermType

    rows = (
        session.query(TermType.type_code)
        .filter(TermType.type_category.in_(sorted(categories)))
        .all()
    )
    return {row.type_code for row in rows}


def _shape_candidates(
    fused: list[Any],
    type_filter: set[str] | frozenset[str] | None,
    *,
    top_k: int,
) -> list[CandidateDict]:
    """将 RRF 融合后的召回结果整形为 CandidateDict 列表。"""
    candidates: list[CandidateDict] = []
    for c in fused:
        if type_filter is not None and c.term_type_code not in type_filter:
            continue
        candidates.append(
            {
                "term_id": c.term_id,
                "term_name": c.term_name,
                "term_type_code": c.term_type_code,
                "match_type": "multi_recall",
                "confidence": min(c.rrf_score * 10, 1.0),
                "score": c.rrf_score,
                "name_id": c.name_id,
                "term_code": getattr(c, "term_code", ""),
            }
        )
        if len(candidates) >= top_k:
            break
    return candidates
