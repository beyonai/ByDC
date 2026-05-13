"""批量召回共享数据模型、常量和协议。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class TypedKeywordState(Protocol):
    keyword: str
    ktype: str
    search_enabled: bool


@dataclass(frozen=True, slots=True)
class RecallRequest:
    map_key: str
    keyword: str
    ktype: str
    type_filter: frozenset[str] | None
    is_per_type: bool
    per_type_limit: int
    scope_code: str | None = None
    is_value_recall: bool = False


@dataclass(frozen=True, slots=True)
class ScopeRecallLayer:
    """A weighted search-scope layer used by layered recall validation."""

    scope_code: str | None
    weight: float = 1.0
    label: str = ""


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    requests: tuple[RecallRequest, ...]
    normal_requests: tuple[RecallRequest, ...]
    per_type_requests: tuple[RecallRequest, ...]


# 向量召回不设最低相似度阈值，统一用 top_k 截断后交给 RRF 融合排序。
# 低质量候选会在 RRF 融合时因排名靠后被自然淘汰。
_BM25_MIN_SCORE = 0.001
_VECTOR_MIN_SIMILARITY = 0.0

# select/groupBy/orderBy/whereKey 不应召回表/视图/动作等非字段类型的术语。
# 这些 ktype 需要的是可查询的字段（prop），而非数据实体定义（object/view/action）。
# 例如："管理网格综合分析表"是 view 类型术语，不应出现在 select 字段候选中。
_FIELD_ONLY_KTYPES: frozenset[str] = frozenset({"select", "groupBy", "orderBy", "whereKey"})
_NON_FIELD_TYPE_CODES: frozenset[str] = frozenset({"view", "object", "action"})

# 单字兜底只允许中文 CJK 字符进入 tsquery。
# 业务上这是最后一道召回兜底，用来处理人名、地名、简称等短文本被 jieba/子串召回漏掉的情况；
# 安全上必须禁止把用户原始输入里的 SQL/tsquery 操作符、英文标识符、标点直接拼进 to_tsquery。
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

# “其他关键字检索都为空”只指文本关键字召回路径：单字 BM25、jieba 词级 BM25、子串召回。
# vector 是语义召回，不属于关键字检索；即使 vector 有弱相关结果，只要关键字路径全空，仍允许单字兜底补充候选。
_KEYWORD_RECALL_PATHS: frozenset[str] = frozenset({"bm25_and", "jieba", "substring"})
