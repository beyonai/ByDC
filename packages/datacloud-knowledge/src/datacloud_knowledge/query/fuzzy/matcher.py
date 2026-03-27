"""模糊匹配器。

基于 rapidfuzz 实现高效模糊匹配：
- 初始化时间：0ms（无需构建索引）
- 查询时间：30-40ms（26K词汇）
- 内存占用：小（只保存词汇列表）

纯函数式风格，所有函数无副作用。
"""

from __future__ import annotations

from typing import FrozenSet, Mapping, Tuple

from .rapidfuzz_matcher import create_rapidfuzz_matcher, rapidfuzz_lookup
from .types import FuzzyMatch, FuzzySuggestion, FuzzyConfig, UnmatchedSpan


def filter_stopwords(
    spans: Tuple[UnmatchedSpan, ...], stopwords: FrozenSet[str]
) -> Tuple[UnmatchedSpan, ...]:
    """过滤停用词片段。

    Args:
        spans: 未匹配片段元组
        stopwords: 停用词集合

    Returns:
        过滤后的未匹配片段元组
    """
    return tuple(span for span in spans if span.text not in stopwords and len(span.text) >= 2)


def match_unmatched_span(
    span: UnmatchedSpan,
    term_metadata: Mapping[str, Tuple[Tuple[str, str, str], ...]],
    config: FuzzyConfig,
) -> FuzzySuggestion:
    """对单个未匹配片段进行模糊匹配。

    Args:
        span: 未匹配片段
        term_metadata: 术语元数据
        config: 配置

    Returns:
        模糊推荐结果
    """
    results = rapidfuzz_lookup(span.text, term_metadata, config)

    matches: list[FuzzyMatch] = []
    for term, similarity, edit_distance in results:
        # 获取术语元数据
        meta_list = term_metadata.get(term, ())
        if meta_list:
            # 取第一个元数据
            term_id, term_type, _ = meta_list[0]
        else:
            term_id, term_type = None, "UNKNOWN"

        # 确定匹配类型
        if similarity == 1.0:
            match_type = "exact"
        elif edit_distance <= 2:
            match_type = "fuzzy"
        else:
            match_type = "approximate"

        matches.append(
            FuzzyMatch(
                term=term,
                term_id=term_id,
                term_type=term_type,
                match_type=match_type,
                similarity=similarity,
                edit_distance=edit_distance,
            )
        )

    return FuzzySuggestion(span=span, matches=tuple(matches))


def match_all_unmatched(
    spans: Tuple[UnmatchedSpan, ...],
    term_metadata: Mapping[str, Tuple[Tuple[str, str, str], ...]],
    config: FuzzyConfig,
    stopwords: FrozenSet[str] = frozenset(),
) -> Tuple[FuzzySuggestion, ...]:
    """对所有未匹配片段进行模糊匹配。

    Args:
        spans: 未匹配片段元组
        term_metadata: 术语元数据
        config: 配置
        stopwords: 停用词集合

    Returns:
        模糊推荐结果元组，仅包含有匹配结果的片段
    """
    # 过滤停用词
    filtered = filter_stopwords(spans, stopwords)

    # 对每个片段进行匹配
    results: list[FuzzySuggestion] = []
    for span in filtered:
        suggestion = match_unmatched_span(span, term_metadata, config)
        if suggestion.matches:  # 只保留有匹配结果的
            results.append(suggestion)

    return tuple(results)


# ============================================================================
# 默认停用词
# ============================================================================

DEFAULT_STOPWORDS: FrozenSet[str] = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        # 常见动词/虚词
        "帮",
        "帮我",
        "看一下",
        "请",
        "查",
        "查一下",
        "找",
        "找一下",
        "一下",
        "哪些",
        "什么",
        "怎么",
        "怎样",
        "如何",
        "多少",
        "几个",
        "第",
        "个",
        "位",
        "家",
        "条",
        "项",
    }
)


# ============================================================================
# 便捷函数
# ============================================================================


def create_matcher(
    term_metadata: Mapping[str, Tuple[Tuple[str, str, str], ...]],
    config: FuzzyConfig | None = None,
    stopwords: FrozenSet[str] | None = None,
) -> Tuple[
    Mapping[str, Tuple[Tuple[str, str, str], ...]],  # term_metadata
    FuzzyConfig,  # config
    FrozenSet[str],  # stopwords
]:
    """创建模糊匹配器所需的全部组件。

    注意：rapidfuzz 不需要预构建索引，此函数返回 term_metadata 以保持接口兼容性。

    Args:
        term_metadata: 术语元数据
        config: 配置（默认使用默认配置）
        stopwords: 停用词集合（默认使用默认停用词）

    Returns:
        (term_metadata, config, stopwords) 元组
    """
    if config is None:
        config = FuzzyConfig()
    if stopwords is None:
        stopwords = DEFAULT_STOPWORDS

    _, config = create_rapidfuzz_matcher(term_metadata, config)
    return (term_metadata, config, stopwords)

