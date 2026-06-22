"""维度值补充识别 — 从复合短语中提取隐含的维度值线索。

cat=3 召回只能找到 prop（字段名），但用户说的"龙头企业数量"里
"龙头"对应 cat=2 字典术语"链主龙头"（维度=企业等级）。
本模块把 cat=2 全量加载到内存，对关键词做子词匹配，产出
dimension_value_hints，供 LLM confirm 作为辅助上下文。

设计原则：
- 不侵入召回管道（typed_recall / batch_recall）
- 结果作为 side-channel，不混入 recall candidates
- cat=2 有界（当前 18 条，预期 ≤ 几百条/域），全量内存安全

数据库访问通过 ``create_reader().get_dimension_values()`` 完成。
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from datacloud_knowledge.adapters import create_reader

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# ── 最小 token 长度：1 字 token 歧义太大，跳过 ────────────
_MIN_TOKEN_LEN = 2


# ── 数据模型 ──────────────────────────────────────────────


class _DimValueReader(Protocol):
    """Reader 协议：仅暴露 resolve_value_to_property / get_referenced_by 所需方法。"""

    def get_relation_target_ids(
        self,
        *,
        source_term_ids: Sequence[str] | None = None,
        target_term_ids: Sequence[str] | None = None,
        relation_category: str | None = None,
    ) -> Sequence[str]: ...

    def get_terms_batch_raw(
        self,
        *,
        term_ids: Sequence[str] | None = None,
        term_codes: Sequence[str] | None = None,
    ) -> Sequence[dict[str, str | None]]: ...


def _get_reader() -> _DimValueReader:
    """获取 reader 并 cast 为内部协议。"""
    return cast(_DimValueReader, create_reader())


@dataclass(frozen=True, slots=True)
class DimValueHint:
    """从短语中识别出的维度值线索。"""

    matched_span: str
    """原始 keyword 中命中的子词（如 "龙头"）。"""

    matched_value: str
    """知识库中的维度值全名（如 "链主龙头"）。"""

    dimension_prop: str
    """所属维度字段名（如 "企业等级"）。"""

    match_type: str
    """匹配类型：exact / contains / token。"""

    confidence: float
    """置信度 0-1。"""


# ── 核心解析器 ─────────────────────────────────────────────


class DimensionValueResolver:
    """维度值索引：懒加载 cat=2 全量到内存，支持子词匹配。

    线程安全、进程生命周期内缓存。
    """

    _instance: DimensionValueResolver | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> DimensionValueResolver:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = cls()
                    inst._load()
                    cls._instance = inst
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试/热更新时重置缓存。"""
        with cls._lock:
            cls._instance = None

    def __init__(self) -> None:
        # {归一化值: (原始值, 维度字段名)}
        self._value_map: dict[str, tuple[str, str]] = {}
        # {维度字段名: [枚举值列表]}
        self._dim_enum: dict[str, list[str]] = {}
        # {prop_name} → 是维度字段（有对应 cat=2 枚举）
        self._dimension_props: set[str] = set()
        self._loaded = False

    def _load(self) -> None:
        """从 DB 加载 cat=2 全量，通过 create_reader() 委托适配器。"""
        if self._loaded:
            return
        try:
            reader = create_reader()
            for item in reader.get_dimension_values():
                val = item.term_name.strip()
                dim = item.type_name.strip()
                if not val or not dim:
                    continue
                normalized = _normalize(val)
                self._value_map[normalized] = (val, dim)
                self._dim_enum.setdefault(dim, []).append(val)
                self._dimension_props.add(dim)

            logger.debug(
                "[dim_values] 加载 cat=2: %d 个维度值, %d 个维度",
                len(self._value_map),
                len(self._dim_enum),
            )
        except Exception:
            logger.warning("[dim_values] 加载 cat=2 失败，维度值识别不可用", exc_info=True)
        self._loaded = True

    # ── 查询接口 ──────────────────────────────────────────

    def match_keyword(self, keyword: str) -> list[DimValueHint]:
        """对关键词做子词匹配，返回命中的维度值线索。

        匹配优先级：exact > contains（值包含 token）> token（token 包含值）。
        同一个维度值只保留最高优先级的匹配。
        """
        if not self._value_map:
            return []

        keyword_normalized = _normalize(keyword)

        # 1. 整词精确匹配
        exact = self._value_map.get(keyword_normalized)
        if exact is not None:
            return [
                DimValueHint(
                    matched_span=keyword,
                    matched_value=exact[0],
                    dimension_prop=exact[1],
                    match_type="exact",
                    confidence=1.0,
                )
            ]

        # 2. 提取子词（jieba 分词 + 字符 n-gram 补充）
        tokens = _extract_tokens(keyword)

        hits: dict[str, DimValueHint] = {}  # keyed by matched_value
        for token in tokens:
            if len(token) < _MIN_TOKEN_LEN:
                continue
            token_norm = _normalize(token)
            for val_norm, (val_orig, dim_name) in self._value_map.items():
                if val_orig in hits:
                    continue  # 已有更高优先级的匹配
                if token_norm == val_norm:
                    # token 精确等于维度值
                    hits[val_orig] = DimValueHint(
                        matched_span=token,
                        matched_value=val_orig,
                        dimension_prop=dim_name,
                        match_type="exact",
                        confidence=1.0,
                    )
                elif token_norm in val_norm:
                    # token 是维度值的子串（"龙头" in "链主龙头"）
                    coverage = len(token_norm) / len(val_norm)
                    hits[val_orig] = DimValueHint(
                        matched_span=token,
                        matched_value=val_orig,
                        dimension_prop=dim_name,
                        match_type="contains",
                        confidence=round(0.5 + coverage * 0.4, 2),
                    )
                elif val_norm in token_norm:
                    # 维度值是 token 的子串（较少见，降权）
                    hits[val_orig] = DimValueHint(
                        matched_span=token,
                        matched_value=val_orig,
                        dimension_prop=dim_name,
                        match_type="token",
                        confidence=0.4,
                    )

        return sorted(hits.values(), key=lambda h: -h.confidence)

    def get_dim_enum(self, dimension_name: str) -> list[str]:
        """获取维度的全部枚举值。"""
        return self._dim_enum.get(dimension_name, [])

    def is_dimension_prop(self, prop_name: str) -> bool:
        """判断 prop 是否为维度字段（有对应 cat=2 枚举值）。"""
        return prop_name in self._dimension_props

    def classify_prop_role(self, prop_name: str) -> str:
        """分类 prop 角色：dimension / measure / unknown。"""
        if self.is_dimension_prop(prop_name):
            return "维度"
        if _looks_like_measure(prop_name):
            return "度量"
        return "unknown"

    # ── 正向/反向属性解析 ──────────────────────────────

    def resolve_value_to_property(self, value_term_id: str) -> dict[str, str]:  # noqa: PLR0911
        """给定 value term_id，解析所属 property 和 object。

        Chain: term_val -> parent -> type_root
               type_root <- HAS_TERM(target) <- prop -> parent -> object

        Args:
            value_term_id: 维度值术语的 term_id（cat=2 枚举项）。

        Returns:
            {"propertyCode": "...", "objectCode": "..."}。
            解析失败时返回空 dict。
        """
        if not value_term_id:
            return {}
        try:
            reader = _get_reader()

            # Step 1: 获取 value term，提取 type_root（parent_term_id）
            value_rows = reader.get_terms_batch_raw(term_ids=[value_term_id])
            if not value_rows:
                return {}
            type_root_id = value_rows[0].get("parent_term_id")
            if not type_root_id:
                return {}

            # Step 2: 查找引用该 type 的 property（反向 HAS_TERM）
            prop_ids = reader.get_relation_target_ids(
                target_term_ids=[type_root_id],
                relation_category="HAS_TERM",
            )
            if not prop_ids:
                return {}

            # Step 3: 取第一个 property，获取其 parent（object）
            prop_rows = reader.get_terms_batch_raw(term_ids=[prop_ids[0]])
            if not prop_rows:
                return {}
            prop_row = prop_rows[0]
            object_id = prop_row.get("parent_term_id")
            if not object_id:
                return {}

            # Step 4: 获取 object
            obj_rows = reader.get_terms_batch_raw(term_ids=[object_id])
            if not obj_rows:
                return {}

            return {
                "propertyCode": prop_row.get("term_code") or "",
                "objectCode": obj_rows[0].get("term_code") or "",
            }
        except Exception:
            logger.warning(
                "[dim_values] resolve_value_to_property 失败: value_term_id=%s",
                value_term_id,
                exc_info=True,
            )
            return {}

    def get_referenced_by(self, value_term_id: str) -> list[dict[str, str]]:  # noqa: PLR0911
        """给定 value term_id，查找所有引用该值类型的 property。

        Chain: term_val -> parent -> type_root
               type_root <- HAS_TERM <- prop -> parent -> object

        Args:
            value_term_id: 维度值术语的 term_id（cat=2 枚举项）。

        Returns:
            [{"objectCode": ..., "objectName": ...,
              "propertyCode": ..., "propertyName": ...}, ...]
        """
        if not value_term_id:
            return []
        try:
            reader = _get_reader()

            # Step 1: 获取 value term，提取 type_root
            value_rows = reader.get_terms_batch_raw(term_ids=[value_term_id])
            if not value_rows:
                return []
            type_root_id = value_rows[0].get("parent_term_id")
            if not type_root_id:
                return []

            # Step 2: 查找所有引用该 type 的 property
            prop_ids = reader.get_relation_target_ids(
                target_term_ids=[type_root_id],
                relation_category="HAS_TERM",
            )
            if not prop_ids:
                return []

            # Step 3: 批量获取 property 详情
            prop_rows = reader.get_terms_batch_raw(term_ids=list(prop_ids))
            if not prop_rows:
                return []

            # Step 4: 收集 object IDs 并批量获取
            object_ids: list[str] = [pid for r in prop_rows if (pid := r.get("parent_term_id"))]
            object_map: dict[str, dict[str, str | None]] = {}
            if object_ids:
                obj_rows = reader.get_terms_batch_raw(term_ids=list(dict.fromkeys(object_ids)))
                for row in obj_rows:
                    tid = row.get("term_id")
                    if tid is not None:
                        object_map[tid] = row

            # Step 5: 组装结果
            results: list[dict[str, str]] = []
            for prop_row in prop_rows:
                obj_id = prop_row.get("parent_term_id")
                obj_row = object_map.get(obj_id) if obj_id else None
                results.append(
                    {
                        "objectCode": (obj_row.get("term_code") or "") if obj_row else "",
                        "objectName": (obj_row.get("term_name") or "") if obj_row else "",
                        "propertyCode": prop_row.get("term_code") or "",
                        "propertyName": prop_row.get("term_name") or "",
                    }
                )
            return results
        except Exception:
            logger.warning(
                "[dim_values] get_referenced_by 失败: value_term_id=%s",
                value_term_id,
                exc_info=True,
            )
            return []


# ── 工具函数 ──────────────────────────────────────────────


_PUNCT_RE = re.compile(r"[\s\u3000（）()【】\[\]{}、，。！？：；\"']+")
_MEASURE_KEYWORDS = frozenset(
    {
        "数量",
        "总数",
        "金额",
        "营收",
        "利润",
        "缴税",
        "均值",
        "平均",
        "占比",
        "比例",
        "增长率",
        "总量",
        "面积",
        "密度",
        "人次",
        "辆次",
        "强度",
        "税负率",
        "效益",
    }
)


def _normalize(text: str) -> str:
    """归一化：去标点空格、统一小写。"""
    return _PUNCT_RE.sub("", text).lower()


def _looks_like_measure(prop_name: str) -> bool:
    """启发式判断 prop 是否像度量。"""
    return any(kw in prop_name for kw in _MEASURE_KEYWORDS)


def _extract_tokens(keyword: str) -> list[str]:
    """从关键词提取子词：jieba.cut_for_search（搜索引擎模式）。

    cut_for_search 自动把长词拆出短词：
      "龙头企业数量" → ["龙头", "企业", "龙头企业", "数量"]
    比 cut + 手动二次拆分更稳定。
    """
    try:
        import jieba

        tokens = list(jieba.cut_for_search(keyword))
    except ImportError:
        # jieba 不可用时退化为 2-gram
        tokens = [keyword[i : i + 2] for i in range(len(keyword) - 1)]

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for raw_token in tokens:
        token = raw_token.strip()
        if token and token not in seen:
            seen.add(token)
            unique.append(token)
    return unique
