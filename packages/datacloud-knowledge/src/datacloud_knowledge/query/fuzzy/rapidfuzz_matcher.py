"""基于 rapidfuzz 的模糊匹配实现。

使用 rapidfuzz 进行高效的中文模糊匹配：
- 初始化时间：0ms（无需构建索引）
- 查询时间：30-40ms（26K词汇）
- 内存占用：小（只保存词汇列表）

纯函数式实现，所有函数无副作用。
"""

from __future__ import annotations

from collections.abc import Mapping

from rapidfuzz import fuzz, process

from .types import FuzzyConfig


def rapidfuzz_lookup(
    query: str,
    term_metadata: Mapping[str, tuple[tuple[str, str, str], ...]],
    config: FuzzyConfig,
) -> tuple[tuple[str, float, int], ...]:
    """使用 rapidfuzz 进行模糊匹配查询。

    Args:
        query: 查询词
        term_metadata: 术语元数据 (term -> ((term_id, term_type, match_type), ...))
        config: 配置

    Returns:
        ((term, similarity, edit_distance), ...) 的元组，按相似度降序排列
    """
    if not query:
        return ()

    candidates = list(term_metadata.keys())
    if not candidates:
        return ()

    # 使用 rapidfuzz 的 extract 进行模糊匹配
    # fuzz.WRatio 综合了多种相似度算法，对中文效果好
    # score_cutoff 设置最低相似度阈值（0-100）
    results_raw = process.extract(
        query,
        candidates,
        scorer=fuzz.WRatio,
        limit=config.max_candidates,
        score_cutoff=config.score_cutoff,
    )

    # 转换结果格式：(term, similarity, edit_distance)
    results: list[tuple[str, float, int]] = []
    for term, score, _ in results_raw:
        # score 是 0-100 的值，转换为 0.0-1.0
        similarity = score / 100.0

        # 计算编辑距离（rapidfuzz 没有直接返回，需要单独计算）
        # 使用 Levenshtein 距离
        from rapidfuzz.distance import Levenshtein

        edit_dist = Levenshtein.distance(query, term)

        results.append((term, similarity, edit_dist))

    return tuple(results)


def create_rapidfuzz_matcher(
    term_metadata: Mapping[str, tuple[tuple[str, str, str], ...]],
    config: FuzzyConfig | None = None,
) -> tuple[Mapping[str, tuple[tuple[str, str, str], ...]], FuzzyConfig]:
    """创建 rapidfuzz 匹配器所需的组件。

    注意：rapidfuzz 不需要预构建索引，此函数仅为保持接口兼容性。

    Args:
        term_metadata: 术语元数据
        config: 配置（默认使用默认配置）

    Returns:
        (term_metadata, config) 元组
    """
    if config is None:
        config = FuzzyConfig()

    # rapidfuzz 不需要构建索引，直接返回 term_metadata
    return (term_metadata, config)
