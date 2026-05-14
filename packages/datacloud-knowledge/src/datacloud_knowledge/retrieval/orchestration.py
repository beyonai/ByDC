"""术语搜索编排 — 精确匹配优先，无结果时 BM25 降级。"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.protocols import TermReader, TermSearchEngine
from datacloud_knowledge.contracts.types import SearchTermsResult, TagFilter

logger = logging.getLogger(__name__)


def search_terms_with_fallback(
    *,
    term_type_code: str,
    keyword: str | None = None,
    tags: Sequence[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
    reader: TermReader | None = None,
    engine: TermSearchEngine | None = None,
) -> SearchTermsResult:
    """精确匹配优先，无结果降级到 BM25 全文搜索。

    编排逻辑：先使用 ``reader.search_terms_exact`` 精确匹配 term_name/term_code，
    零结果时自动降级到 ``reader.search_terms``（内置 BM25 兜底）。
    ``reader`` / ``engine`` 参数支持依赖注入（测试用），``None`` 则使用工厂默认实例。

    注意：当前 BM25 降级通过 ``reader.search_terms`` 实现（折旧方法），
    待 engine session 管理统一后迁移为直接调用 ``engine.search_bm25``。

    Args:
        term_type_code: 术语类型编码（支持驼峰简写映射，如 ONTOLOGY_VIEW→view）。
        keyword: 可选关键词（精确匹配 term_name/term_code）。
        tags: 可选标签过滤条件列表。
        limit: 返回条数（1..200）。
        offset: 分页偏移（>=0）。
        order_by: 排序方式（relevance/updated_time/created_time/term_name）。
        reader: TermReader 实例（可选，默认工厂创建）。
        engine: TermSearchEngine 实例（可选，预留，当前未使用）。

    Returns:
        SearchTermsResult，包含 total 和 items。无匹配时 total=0。
    """
    if reader is None:
        reader = create_reader()
    del engine  # 预留，待 engine session 管理统一后启用

    # Step 1: 精确匹配
    result = reader.search_terms_exact(
        term_type_code=term_type_code,
        keyword=keyword,
        tags=list(tags) if tags else None,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    if result.total > 0 or not keyword:
        return result

    # Step 2: BM25 兜底
    logger.info("精确匹配无结果，降级 BM25: type=%s keyword=%s", term_type_code, keyword)
    return reader.search_terms(
        term_type_code=term_type_code,
        keyword=keyword,
        tags=list(tags) if tags else None,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
