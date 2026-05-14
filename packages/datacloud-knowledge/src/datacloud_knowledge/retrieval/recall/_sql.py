"""批量召回 SQL 构建层 — 已迁移至 adapters.opengauss.engine 模块。

所有 SQL 构建与执行函数已移入 PostgresSearchEngine（模块级辅助函数），
本文件保留为兼容性转发桩。
"""

from datacloud_knowledge.adapters.opengauss.engine import (  # noqa: F401
    _build_effective_scope_clause,
    _build_scope_params,
    _build_substring_sql,
    _build_tsquery_sql,
    _build_values_clause,
    _build_vector_sql,
    _collect_ranked_rows,
    _group_requests_by_filter,
)
