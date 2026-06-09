"""Layer 1 — 查询组合模式（纯函数）。

所有函数只依赖 TermStore Protocol，不 import adapters/ 内部模块。
每个函数封装一组 TermStore.query_terms() 参数组合，形成可复用的查询原子。
"""

from __future__ import annotations

from datacloud_knowledge.capabilities.protocol import TermStore
from datacloud_knowledge.capabilities.types import LabelFilter, QueryResult

__all__ = [
    "query_bound_values",
    "query_scope_props",
    "query_user_synonyms",
]


def query_scope_props(store: TermStore, scope_code: str) -> QueryResult:
    """查询指定 scope 下的所有属性术语。

    等价于::

        store.query_terms(
            term_type=[scope_code],
            label_filters=[LabelFilter("termDataType", "prop")],
        )

    用于"查视图下属性"（ARCHITECTURE_V2.md 功能1）。
    HTTP API 侧 term_type 支持 Array，labelFilter 过滤 termDataType=prop。

    Args:
        store:      TermStore 实例。
        scope_code: scope 术语编码（如 ``"scene_enterprise_analysis"``）。

    Returns:
        QueryResult，items 为该 scope 下的所有 prop 术语。
    """
    return store.query_terms(
        term_type=[scope_code] if scope_code else None,
        label_filters=[LabelFilter(field_code="termDataType", filter_value="prop")],
        top_k=500,
    )


def query_bound_values(store: TermStore, binding_codes: list[str]) -> QueryResult:
    """查询指定绑定编码对应的值术语。

    等价于::

        store.query_terms(term_type=binding_codes)

    用于"查属性枚举值"（通过 termBinding 获取枚举值列表）。
    HTTP API 侧 term_type 支持 Array 传入多个 term_code 批量查询。

    Args:
        store:         TermStore 实例。
        binding_codes: 值术语编码列表（从 prop 的 termBinding 中提取）。

    Returns:
        QueryResult，items 为绑定编码对应的值术语。
    """
    return store.query_terms(
        term_type=binding_codes if binding_codes else None,
        top_k=500,
    )


def query_user_synonyms(store: TermStore, user_id: str) -> QueryResult:
    """查询指定用户的自定义同义词。

    等价于::

        store.query_terms(
            term_type="synonym",
            label_filters=[LabelFilter("userId", user_id)],
        )

    用于"按用户查术语"（ARCHITECTURE_V2.md 功能4）。
    通过 userId 标签过滤同义词类型的术语。

    Args:
        store:   TermStore 实例。
        user_id: 用户标识。

    Returns:
        QueryResult，items 为该用户的同义词术语。
    """
    return store.query_terms(
        term_type="synonym",
        label_filters=[LabelFilter(field_code="userId", filter_value=user_id)],
        top_k=500,
    )
