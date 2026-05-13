"""批量并发术语召回子包。

拆分自 batch_recall.py，按职责分为：
- _models: 数据模型与常量
- _paths: 四路召回路径（BM25 / jieba / 子串 / 向量）
- _fusion: RRF 融合与候选整形
- _scope: 分层 scope 召回管理
- _orchestrator: 编排与主入口
"""

from ._fusion import (  # noqa: F401
    _add_single_char_fallback_results,
    _all_existing_paths_empty,
    _batch_single_char_fallback,
    _build_single_char_fallback_batch,
    _dedupe_candidates_by_term_name,
    _dedupe_ranked_rows_by_term_name,
    _fuse_and_shape,
    _post_filter_non_field_types,
    _shape_diversified_candidates,
    _single_char_fallback_tsquery,
)
from ._models import (  # noqa: F401
    _BM25_MIN_SCORE,
    _CJK_CHAR_RE,
    _FIELD_ONLY_KTYPES,
    _KEYWORD_RECALL_PATHS,
    _NON_FIELD_TYPE_CODES,
    _VECTOR_MIN_SIMILARITY,
    PreparedBatch,
    RecallRequest,
    ScopeRecallLayer,
    TypedKeywordState,
)
from ._orchestrator import (  # noqa: F401
    _prepare_batch,
    _run_paths_concurrent,
    typed_multi_recall_batch,
)
from ._paths import (  # noqa: F401
    _batch_bm25_and,
    _batch_jieba_bm25,
    _batch_substring,
    _batch_vector,
    _run_single_vector_query,
    _run_tsquery_batches,
)
from ._scope import (  # noqa: F401
    _add_layered_single_char_fallback_results,
    _all_layer_keyword_paths_empty,
    _candidate_top_names,
    _filter_batch_by_map_keys,
    _normalize_scope_layers,
    _preserve_base_layer_candidate,
    _typed_multi_recall_layered,
    _weighted_fuse_candidate_layers,
)
from ._sql import (  # noqa: F401
    _build_effective_scope_clause,
    _build_scope_params,
    _build_substring_sql,
    _build_tsquery_sql,
    _build_values_clause,
    _build_vector_sql,
    _collect_ranked_rows,
    _group_requests_by_filter,
)

__all__ = [
    "PreparedBatch",
    "RecallRequest",
    "ScopeRecallLayer",
    "TypedKeywordState",
    "typed_multi_recall_batch",
]
